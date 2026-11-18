#!/usr/bin/env bash
# Pin Sellbird's image in a platform overlay by commit SHA and digest, with guards.
#
# A pure function over two git checkouts and the inputs: it edits one file in the
# overlay checkout and makes one local commit, or refuses and leaves that
# checkout exactly as it found it. It never pushes, fetches or touches the network;
# the deploy job (.github/workflows/images.yml, job `deploy`) pushes and retries.
#
# Usage:
#   scripts/deploy/pin_overlay.sh \
#     --overlay-repo <dir>   checkout of the platform repository (clean worktree)
#     --source-repo  <dir>   checkout of this repository with full main history
#     --tag          <sha>   40-hex commit SHA the image was built from
#     --digest       <dgst>  sha256:<64 hex> manifest digest of the pushed image
#     [--image <name>]       expected newName, e.g. ghcr.io/<owner>/sellbird
#     [--file <relpath>]     default apps/sellbird/overlays/production/kustomization.yaml
#
# Exit codes: 0 pinned (one local commit made); 3 already pinned to this tag and
# digest (nothing to do); 1 refused (nothing changed); 2 usage error.
#
# Contract (docs/platform-interface.md, "Overlay location and pin format"):
#   - inputs validated by regex before anything is read or written;
#   - the overlay holds exactly one images entry for `sellbird`, in a FIXED LINE
#     ORDER the guard relies on:
#         - name: sellbird
#           newName: <registry>/<owner>/sellbird
#           newTag: "<40 hex>"
#           digest: sha256:<64 hex>
#     anything else (a tag-only entry with no digest line, extra newTag/digest
#     lines, reordered keys) is refused;
#   - never backwards: the pinned SHA must be a strict ancestor of the new SHA in
#     the source repository (same SHA and digest: nothing to do);
#   - the commit changes exactly the newTag and digest lines, each new line lands
#     exactly once, and no other file changes.
#
# Portable to bash 3.2 and BSD/GNU tools. The caller sets the commit identity.

set -u -o pipefail

SHA_RE='^[0-9a-f]{40}$'
DIGEST_RE='^sha256:[0-9a-f]{64}$'
IMAGE_RE='^ghcr\.io/[a-z0-9]([a-z0-9-]*[a-z0-9])?/sellbird$'
NAME=sellbird

OVERLAY_REPO=""
SOURCE_REPO=""
TAG=""
DIGEST=""
IMAGE=""
FILE="apps/sellbird/overlays/production/kustomization.yaml"
HAVE_DIGEST=0

usage() {
  sed -n '2,20p' "$0" >&2
  exit 2
}

refuse() {
  echo "pin_overlay: refused: $*" >&2
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --overlay-repo) [ "$#" -ge 2 ] || usage; OVERLAY_REPO=$2; shift 2 ;;
    --source-repo)  [ "$#" -ge 2 ] || usage; SOURCE_REPO=$2; shift 2 ;;
    --tag)          [ "$#" -ge 2 ] || usage; TAG=$2; shift 2 ;;
    --digest)       [ "$#" -ge 2 ] || usage; DIGEST=$2; HAVE_DIGEST=1; shift 2 ;;
    --image)        [ "$#" -ge 2 ] || usage; IMAGE=$2; shift 2 ;;
    --file)         [ "$#" -ge 2 ] || usage; FILE=$2; shift 2 ;;
    -h|--help)      usage ;;
    *) echo "pin_overlay: unknown argument: $1" >&2; usage ;;
  esac
done

[ -n "$OVERLAY_REPO" ] && [ -n "$SOURCE_REPO" ] && [ -n "$TAG" ] || usage

# 1. Inputs, before touching anything.
[[ "$TAG" =~ $SHA_RE ]] || refuse "tag is not a 40-character lowercase commit SHA"
[ "$HAVE_DIGEST" -eq 1 ] && [ -n "$DIGEST" ] \
  || refuse "no digest given: a tag-only image is never pinned"
[[ "$DIGEST" =~ $DIGEST_RE ]] || refuse "digest is not sha256:<64 lowercase hex>"
if [ -n "$IMAGE" ]; then
  [[ "$IMAGE" =~ $IMAGE_RE ]] || refuse "image name is not ghcr.io/<owner>/sellbird"
fi
case "$FILE" in
  /*|*..*|"") refuse "file must be a relative path inside the overlay repository" ;;
esac

# 2. Repositories and file.
git -C "$OVERLAY_REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || refuse "overlay repository is not a git checkout"
git -C "$SOURCE_REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || refuse "source repository is not a git checkout"
TARGET="$OVERLAY_REPO/$FILE"
[ -f "$TARGET" ] && [ ! -L "$TARGET" ] || refuse "$FILE is missing or not a regular file"
[ -z "$(git -C "$OVERLAY_REPO" status --porcelain)" ] \
  || refuse "overlay checkout has uncommitted changes"
[ "$(tail -c 1 "$TARGET" | od -An -c | tr -d ' ')" = '\n' ] \
  || refuse "$FILE does not end with a newline"
if LC_ALL=C grep -q "$(printf '\r')" "$TARGET"; then
  refuse "$FILE has CRLF line endings"
fi

count_lines() {  # count_lines <ERE> : matching lines in the target
  LC_ALL=C grep -cE -- "$1" "$TARGET" || true
}

# 3. The images entry, in its fixed line order.
NAME_LINE="  - name: $NAME"
name_count="$(LC_ALL=C grep -cxF -- "$NAME_LINE" "$TARGET" || true)"
[ "$name_count" -eq 1 ] || refuse "expected exactly one '$NAME_LINE' line, found $name_count"
[ "$(count_lines '^[[:space:]]*newTag:')" -eq 1 ] \
  || refuse "expected exactly one newTag line in $FILE"
[ "$(count_lines '^[[:space:]]*digest:')" -eq 1 ] \
  || refuse "expected exactly one digest line in $FILE (a tag-only image is refused)"

L="$(LC_ALL=C grep -nxF -- "$NAME_LINE" "$TARGET" | cut -d: -f1)"
line_at() { sed -n "$1p" "$TARGET"; }
newname_line="$(line_at $((L + 1)))"
newtag_line="$(line_at $((L + 2)))"
digest_line="$(line_at $((L + 3)))"

[[ "$newname_line" =~ ^\ \ \ \ newName:\ ([^[:space:]]+)$ ]] \
  || refuse "entry is not in the fixed order name, newName, newTag, digest (line $((L + 1)))"
current_name="${BASH_REMATCH[1]}"
[[ "$newtag_line" =~ ^\ \ \ \ newTag:\ \"?([0-9a-f]{40})\"?$ ]] \
  || refuse "entry is not in the fixed order name, newName, newTag, digest, or newTag is not a SHA (line $((L + 2)))"
current_tag="${BASH_REMATCH[1]}"
[[ "$digest_line" =~ ^\ \ \ \ digest:\ (sha256:[0-9a-f]{64})$ ]] \
  || refuse "entry has no well-formed digest line after newTag (a tag-only image is refused)"
current_digest="${BASH_REMATCH[1]}"

if [ -n "$IMAGE" ] && [ "$current_name" != "$IMAGE" ]; then
  refuse "overlay newName '$current_name' is not the published image '$IMAGE'"
fi

# 4. Never backwards.
if [ "$current_tag" = "$TAG" ]; then
  if [ "$current_digest" = "$DIGEST" ]; then
    echo "pin_overlay: already pinned to $TAG $DIGEST; nothing to do"
    exit 3
  fi
  refuse "tag $TAG is already pinned with a different digest; tags are immutable"
fi
git -C "$SOURCE_REPO" cat-file -e "$TAG^{commit}" 2>/dev/null \
  || refuse "new tag $TAG is not a commit in the source repository"
git -C "$SOURCE_REPO" cat-file -e "$current_tag^{commit}" 2>/dev/null \
  || refuse "pinned tag $current_tag is not a commit in the source repository"
if ! git -C "$SOURCE_REPO" merge-base --is-ancestor "$current_tag" "$TAG"; then
  if git -C "$SOURCE_REPO" merge-base --is-ancestor "$TAG" "$current_tag"; then
    refuse "refusing to move backwards: $TAG is older than the pinned $current_tag"
  fi
  refuse "pinned $current_tag is not an ancestor of $TAG (diverged history)"
fi

# 5. Rewrite into a temporary file and check the difference before installing it.
TMP="$(mktemp "${TMPDIR:-/tmp}/pin_overlay.XXXXXX")" || refuse "cannot create a temporary file"
INSTALLED=0
cleanup() {
  status=$?
  rm -f "$TMP"
  if [ "$INSTALLED" -eq 1 ] && [ "$status" -ne 0 ]; then
    git -C "$OVERLAY_REPO" checkout -q -- "$FILE" 2>/dev/null
  fi
}
trap cleanup EXIT

NEW_TAG_LINE="    newTag: \"$TAG\""
NEW_DIGEST_LINE="    digest: $DIGEST"
awk -v a=$((L + 2)) -v b=$((L + 3)) -v t="$NEW_TAG_LINE" -v d="$NEW_DIGEST_LINE" \
  'NR == a { print t; next } NR == b { print d; next } { print }' "$TARGET" > "$TMP" \
  || refuse "rewrite failed"

changed="$(diff "$TARGET" "$TMP" | grep -E '^[<>] ' || true)"
removed="$(printf '%s\n' "$changed" | grep -c '^< ' || true)"
added="$(printf '%s\n' "$changed" | grep -c '^> ' || true)"
[ "$removed" -eq 2 ] && [ "$added" -eq 2 ] \
  || refuse "pin would change $removed old and $added new lines; expected exactly 2 and 2"
if printf '%s\n' "$changed" | grep -Ev '^[<>]     (newTag|digest): ' | grep -q .; then
  refuse "pin would change a line other than newTag or digest"
fi
[ "$(wc -l < "$TARGET")" -eq "$(wc -l < "$TMP")" ] || refuse "line count would change"
[ "$(LC_ALL=C grep -cxF -- "$NEW_TAG_LINE" "$TMP" || true)" -eq 1 ] \
  || refuse "new newTag line would not land exactly once"
[ "$(LC_ALL=C grep -cxF -- "$NEW_DIGEST_LINE" "$TMP" || true)" -eq 1 ] \
  || refuse "new digest line would not land exactly once"

# 6. Install, re-check through git, commit.
INSTALLED=1
cat "$TMP" > "$TARGET" || refuse "cannot write $FILE"
[ "$(git -C "$OVERLAY_REPO" diff --name-only)" = "$FILE" ] \
  || refuse "git sees changes outside $FILE"
[ "$(git -C "$OVERLAY_REPO" diff --numstat -- "$FILE" | cut -f1,2)" = "$(printf '2\t2')" ] \
  || refuse "git does not see exactly two changed lines"
[ -z "$(git -C "$OVERLAY_REPO" status --porcelain --untracked-files=all | grep -v " $FILE\$" || true)" ] \
  || refuse "unexpected files in the overlay checkout"

git -C "$OVERLAY_REPO" commit -q -m "chore(sellbird): pin $TAG $DIGEST" -- "$FILE" \
  || refuse "commit failed"
INSTALLED=0

echo "pin_overlay: pinned $current_name:$TAG@$DIGEST (was $current_tag)"
exit 0
