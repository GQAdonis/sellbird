#!/usr/bin/env bash
# SCN-REG-001 negative control: for each of the five code tasks, revert that task's production
# edit in a scratch `git worktree` and require that task's required tests to FAIL there while the
# other four tasks' required tests still PASS ("and only those"). Packet: neg-reg.sh SCN-REG-001.
#
# Task -> production files (reverted to their content at the base commit, which is
# $GOLIVE_BASE_REF, else the merge-base of HEAD and origin/main; the working tree is never patched):
#   hosted-small-fixes/1   sellbird/auth/config.py                 (JWKS address rule)
#   hosted-small-fixes/2   sellbird/storage_postgres/__init__.py   (exists() contract)
#   hosted-heartbeat/1     sellbird/main.py                        (setup check, cycle rows)
#   hosted-heartbeat/2     sellbird/state.py, sellbird/dashboard.py (last_heartbeat_at, status)
#   hosted-heartbeat/3     sellbird/web/app.js                     (hosted status view)
# hosted-small-fixes/3 (compose port variable) has no code test and is not part of this control.
# dashboard.py and state.py are edited by hosted-heartbeat/2 only; web/app.js by /3 only, so no
# production file is shared between tasks. Each worktree is created from HEAD (committed work), so
# uncommitted edits are not seen: preflight.sh refuses a dirty tree. One pytest run per worktree
# covers all five tasks' IDs; _junit.py judges per task. The worktree's own package must be the
# one imported (editable installs can point back at the main checkout): checked and reported.
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin negativeControl SCN-REG-001
cd "$GOLIVE_ROOT"

golive_require_tools git
golive_require_venv pytest pytest_asyncio psycopg yaml
golive_load_ports
if ! golive_pg_dsns_export; then
  golive_finish BLOCKED "the local stand-in is not prepared (no infra/local/.env): run standin-up.sh first"
fi
dirty="$(golive_relevant_dirty | wc -l | tr -d ' ')"
if [ "$dirty" -gt 0 ] && [ -z "${GOLIVE_ALLOW_DIRTY:-}" ]; then
  golive_finish BLOCKED "$dirty uncommitted paths: the scratch worktrees are made from HEAD; commit first"
fi
if ! base="$(golive_base_sha)"; then
  golive_finish BLOCKED "no base commit: set GOLIVE_BASE_REF to the pre-phase commit"
fi

task_files() {
  case "$1" in
    hosted-small-fixes/1) echo "sellbird/auth/config.py" ;;
    hosted-small-fixes/2) echo "sellbird/storage_postgres/__init__.py" ;;
    hosted-heartbeat/1) echo "sellbird/main.py" ;;
    hosted-heartbeat/2) echo "sellbird/state.py sellbird/dashboard.py" ;;
    hosted-heartbeat/3) echo "sellbird/web/app.js" ;;
  esac
}
TASKS="hosted-small-fixes/1 hosted-small-fixes/2 hosted-heartbeat/1 hosted-heartbeat/2 hosted-heartbeat/3"

ids=()
while IFS= read -r line; do
  ids+=("$line")
done < <("$GOLIVE_PY" -I "$GOLIVE_DIR/_junit.py" ids "$GOLIVE_FIXTURE")
if [ "${#ids[@]}" -eq 0 ]; then
  golive_finish BLOCKED "the fixture lists no required tests"
fi

golive_scratch_new
parent="$GOLIVE_LAST_SCRATCH"
bad=0
for task in $TASKS; do
  slug="$(printf '%s' "$task" | tr '/' '-')"
  wt="$parent/wt-$slug"
  git -C "$GOLIVE_ROOT" worktree add --detach --quiet "$wt" HEAD
  GOLIVE_WORKTREES+=("$wt")
  changed=0
  for f in $(task_files "$task"); do
    before="$(golive_sha256 "$wt/$f")"
    if git -C "$GOLIVE_ROOT" cat-file -e "$base:$f" 2> /dev/null; then
      git -C "$GOLIVE_ROOT" show "$base:$f" > "$wt/$f"
    else
      rm -f "$wt/$f"
    fi
    if [ ! -f "$wt/$f" ] || [ "$(golive_sha256 "$wt/$f")" != "$before" ]; then
      changed=$((changed + 1))
    fi
  done
  if [ "$changed" -eq 0 ]; then
    record_detail SCN-REG-001 NOT_EXERCISED "$task: its production files are identical at the base commit and HEAD, so there is nothing to revert"
    bad=$((bad + 1))
    continue
  fi
  imported="$(cd "$wt" && PYTHONPATH="$wt" "$GOLIVE_PY" -c 'import sellbird; print(sellbird.__file__)' 2> /dev/null || true)"
  case "$imported" in
    "$wt"/*) ;;
    *)
      record_detail SCN-REG-001 FAIL "$task: the worktree does not import its own sellbird package (harness defect, not a product result)"
      bad=$((bad + 1))
      continue
      ;;
  esac
  xml="$(golive_artifact "neg-reg-$slug-junit.xml")"
  raw="$(golive_artifact "raw-neg-reg-$slug.log")"
  rc=0
  (cd "$wt" && PYTHONPATH="$wt" "${GOLIVE_CLEAN_ENV[@]}" "$GOLIVE_PY" -m pytest -q -rs -p no:cacheprovider \
    --junitxml="$xml" "${ids[@]}") >> "$raw" 2>&1 || rc=$?
  if [ ! -s "$xml" ]; then
    record_detail SCN-REG-001 FAIL "$task: pytest produced no junit file (exit $rc)"
    bad=$((bad + 1))
    continue
  fi
  # This task's tests must fail ...
  if "$GOLIVE_PY" -I "$GOLIVE_DIR/_junit.py" required "$xml" "$GOLIVE_FIXTURE" --root "$wt" --task "$task" --expect fail > "$raw.task" 2>&1; then
    mine=rejected
  else
    mine=NOT-rejected
  fi
  # ... and every other task's tests must still pass.
  others_bad=""
  for other in $TASKS; do
    if [ "$other" = "$task" ]; then
      continue
    fi
    if ! "$GOLIVE_PY" -I "$GOLIVE_DIR/_junit.py" required "$xml" "$GOLIVE_FIXTURE" --root "$wt" --task "$other" --expect pass > /dev/null 2>&1; then
      others_bad="$others_bad $other"
    fi
  done
  if [ "$mine" = rejected ] && [ -z "$others_bad" ]; then
    record_detail SCN-REG-001 PASS "$task: reverting its edit makes its required tests fail; the other four tasks' tests still pass"
  else
    bad=$((bad + 1))
    record_detail SCN-REG-001 FAIL "$task: its tests were $mine by the revert; other tasks' tests failing there:${others_bad:- none}"
  fi
  git -C "$GOLIVE_ROOT" worktree remove --force "$wt" > /dev/null 2>&1 || true
done

if [ "$bad" -gt 0 ]; then
  golive_finish FAIL "$bad of 5 tasks did not show the expected rejection (see results.jsonl)"
fi
golive_finish PASS "all 5 reverted-edit worktrees fail exactly their own task's required tests"
