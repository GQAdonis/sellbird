#!/usr/bin/env bash
# Boundary check for the container-runtime spec
# (openspec/changes/cluster-ready-container-image/specs/container-runtime/spec.md).
#
#   scripts/boundary/check_container.sh [--brain] <image>
#
# Runs the image the way the hosted deployment does (read-only root
# filesystem, tmpfs /tmp, a /data volume, all capabilities dropped) and checks:
#   - the image user is not root, and the running process is not uid 0;
#   - docker inspect reports ReadonlyRootfs=true; /app is not writable, /data is;
#   - the image's HEALTHCHECK (a TCP connect) turns healthy in local mode and in
#     gateway mode, and gateway mode answers a request without the public Host
#     with 400 (why the probes must be tcpSocket, not httpGet);
#   - a generated dummy CLAUDE_CODE_OAUTH_TOKEN and the dashboard token the
#     container generates appear in no container log, and the dummy credential
#     appears in no file under /data, $HOME or /tmp;
#   - no Claude credentials file exists under /data, $HOME or CLAUDE_CONFIG_DIR.
# With --brain it also checks, through sellbird.brain.Brain itself:
#   - with CLAUDE_CODE_OAUTH_TOKEN set, the claude subprocess receives exactly
#     that value (a stand-in `claude` reports its SHA-256, never the value);
#   - with it unset, the pinned real CLI (no network, empty config directory)
#     fails and the brain logs its documented missing-login error,
#     "Non-retryable Claude error (auth)", with no credential file to fall back to.
#
# Every value used here is generated per run and is not a real credential.
# Needs only Docker on the host. Exit status: 0 all checks passed, 1 a check
# failed, 2 usage or setup error.
set -euo pipefail

usage() { echo "usage: $0 [--brain] <image>" >&2; exit 2; }

BRAIN=0
IMAGE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --brain) BRAIN=1; shift ;;
    -h|--help) usage ;;
    -*) usage ;;
    *) [[ -z "$IMAGE" ]] || usage; IMAGE="$1"; shift ;;
  esac
done
[[ -n "$IMAGE" ]] || usage
command -v docker >/dev/null 2>&1 || { echo "check_container: docker is required" >&2; exit 2; }
docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "check_container: no local image $IMAGE" >&2; exit 2; }

RUN_ID="sbcheck-$$-$(date +%s)"
FAILURES=0
CONTAINERS=()
VOLUMES=()

cleanup() {
  local c v
  for c in "${CONTAINERS[@]:-}"; do [[ -n "$c" ]] && docker rm -f "$c" >/dev/null 2>&1 || true; done
  for v in "${VOLUMES[@]:-}"; do [[ -n "$v" ]] && docker volume rm -f "$v" >/dev/null 2>&1 || true; done
}
trap cleanup EXIT

pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; FAILURES=$((FAILURES + 1)); }

random_hex() { od -An -tx1 -N"$1" /dev/urandom | tr -d ' \n'; }
sha256_of() { printf '%s' "$1" | { sha256sum 2>/dev/null || shasum -a 256; } | cut -d' ' -f1; }

# Obviously fake, unique per run.
DUMMY_CLAUDE_TOKEN="sk-ant-oat01-boundary-dummy-$(random_hex 24)"
DUMMY_CLAUDE_SHA256="$(sha256_of "$DUMMY_CLAUDE_TOKEN")"

# The hosted runtime: read-only root, tmpfs /tmp (exec, like a Kubernetes
# emptyDir), no capabilities, no privilege escalation.
HARDENING=(
  --read-only
  --tmpfs /tmp:rw,nosuid,nodev,exec,size=512m
  --cap-drop ALL
  --security-opt no-new-privileges
)

# Placeholder gateway configuration (example.test only; the JWKS is never
# fetched because no request carries a token).
GATEWAY_ENV=(
  -e SELLBIRD_DASHBOARD_MODE=gateway
  -e SELLBIRD_PUBLIC_HOST=sellbird.example.test
  -e SELLBIRD_GATE_ISSUER=https://gate.example.test
  -e SELLBIRD_GATE_AUDIENCE=sellbird
  -e SELLBIRD_GATE_JWKS_URL=http://flint-gate.flint-gate.svc.cluster.local:4456/.well-known/jwks.json
  -e SELLBIRD_GATE_ALLOWED_SUBS=00000000-0000-4000-8000-000000000001
)

wait_healthy() {  # <container> <seconds>
  local c="$1" deadline=$((SECONDS + $2)) status
  while (( SECONDS < deadline )); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$c" 2>/dev/null || true)"
    [[ "$status" == "healthy" ]] && return 0
    [[ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null || echo false)" == "true" ]] || return 1
    sleep 2
  done
  return 1
}

# Starts a dashboard container with a fresh /data volume. Health is polled
# faster than the image default; the command itself is the image's.
start_dashboard() {  # <name> [extra docker args...] -- [command args...]
  local name="$1"; shift
  local vol="${name}-data"
  docker volume create "$vol" >/dev/null
  VOLUMES+=("$vol")
  local opts=() cmd=()
  while [[ $# -gt 0 && "$1" != "--" ]]; do opts+=("$1"); shift; done
  [[ "${1:-}" == "--" ]] && shift
  cmd=("$@")
  docker run -d --name "$name" "${HARDENING[@]}" \
    -v "$vol:/data" \
    --health-interval 2s --health-timeout 5s --health-start-period 5s --health-retries 30 \
    -e CLAUDE_CODE_OAUTH_TOKEN="$DUMMY_CLAUDE_TOKEN" \
    ${opts[@]+"${opts[@]}"} "$IMAGE" ${cmd[@]+"${cmd[@]}"} >/dev/null
  CONTAINERS+=("$name")
}

# Search files for a value without placing it in any process's argv inside the
# container: grep reads the pattern from stdin (-f -). Prints file names only.
grep_files_for() {  # <container> <value> <paths...>
  local c="$1" value="$2"; shift 2
  printf '%s\n' "$value" | docker exec -i "$c" grep -rlIF -f - "$@" 2>/dev/null || true
}

logs_contain() {  # <container> <value>
  docker logs "$1" 2>&1 | grep -qF -- "$2"
}

# ---------------------------------------------------------------------------
echo "== image $IMAGE"
IMG_USER="$(docker image inspect -f '{{.Config.User}}' "$IMAGE")"
case "$IMG_USER" in
  ""|root|0|0:*|root:*) fail "image user is root or unset (Config.User='$IMG_USER')" ;;
  *) pass "image user is non-root (Config.User='$IMG_USER')" ;;
esac
for label in org.opencontainers.image.source org.opencontainers.image.revision org.opencontainers.image.version; do
  val="$(docker image inspect -f "{{index .Config.Labels \"$label\"}}" "$IMAGE")"
  if [[ -n "$val" ]]; then pass "label $label=$val"; else fail "label $label missing"; fi
done

# ---------------------------------------------------------------------------
echo "== local mode (default command)"
LOCAL="${RUN_ID}-local"
start_dashboard "$LOCAL" --network none --
if wait_healthy "$LOCAL" 120; then
  pass "HEALTHCHECK healthy in local mode"
else
  fail "HEALTHCHECK not healthy in local mode"
fi

if [[ "$(docker inspect -f '{{.HostConfig.ReadonlyRootfs}}' "$LOCAL")" == "true" ]]; then
  pass "running container has ReadonlyRootfs=true"
else
  fail "running container is not read-only"
fi
RUN_UID="$(docker exec "$LOCAL" id -u)"
if [[ "$RUN_UID" != "0" ]]; then pass "process uid is $RUN_UID"; else fail "process runs as uid 0"; fi
if docker exec "$LOCAL" sh -c 'touch /app/.sb-write-test' >/dev/null 2>&1; then
  fail "/app is writable"
else
  pass "/app is not writable"
fi
if docker exec "$LOCAL" sh -c 'touch /data/.sb-write-test && rm /data/.sb-write-test' >/dev/null 2>&1; then
  pass "/data is writable"
else
  fail "/data is not writable"
fi
if docker exec "$LOCAL" test -f /data/sellbird.yaml; then
  pass "defaults seeded into /data"
else
  fail "/data/sellbird.yaml was not seeded"
fi

# The dashboard token the container generated (local mode creates it). It is a
# throwaway for this test container; it stays in this shell variable only.
DASH_TOKEN="$(docker exec "$LOCAL" cat /data/data/dashboard-token 2>/dev/null || true)"
DASH_TOKEN="${DASH_TOKEN//[[:space:]]/}"
if [[ -n "$DASH_TOKEN" ]]; then
  pass "local mode generated a dashboard token file"
  if logs_contain "$LOCAL" "$DASH_TOKEN"; then fail "dashboard token appears in local-mode logs"; else pass "dashboard token absent from local-mode logs"; fi
else
  fail "no dashboard token at /data/data/dashboard-token"
fi
if logs_contain "$LOCAL" "#token="; then fail "an unlock link appears in local-mode logs"; else pass "no unlock link in local-mode logs"; fi
if logs_contain "$LOCAL" "$DUMMY_CLAUDE_TOKEN"; then fail "dummy CLAUDE_CODE_OAUTH_TOKEN appears in local-mode logs"; else pass "dummy credential absent from local-mode logs"; fi
HITS="$(grep_files_for "$LOCAL" "$DUMMY_CLAUDE_TOKEN" /data /home/sellbird /tmp)"
if [[ -z "$HITS" ]]; then pass "dummy credential in no file under /data, \$HOME, /tmp"; else fail "dummy credential found in: $HITS"; fi
CREDS="$(docker exec "$LOCAL" sh -c 'find /data /home/sellbird "${CLAUDE_CONFIG_DIR:-/nonexistent}" -name .credentials.json 2>/dev/null' || true)"
if [[ -z "$CREDS" ]]; then pass "no Claude credentials file"; else fail "Claude credentials file present: $CREDS"; fi
URL_OUT="$(docker exec "$LOCAL" python -m sellbird dashboard --url 2>&1 || true)"
if grep -qF '#token=' <<<"$URL_OUT"; then
  fail "dashboard --url printed a link inside the container"
else
  pass "dashboard --url prints no link inside the container"
fi
unset URL_OUT

# ---------------------------------------------------------------------------
echo "== gateway mode (selected by environment only)"
GW="${RUN_ID}-gateway"
start_dashboard "$GW" --network none "${GATEWAY_ENV[@]}" -- dashboard --host 0.0.0.0 --port 5555
if wait_healthy "$GW" 120; then
  pass "HEALTHCHECK (TCP) healthy in gateway mode"
else
  fail "HEALTHCHECK not healthy in gateway mode"
fi
GW_STATUS="$(docker exec "$GW" python -c '
import urllib.error, urllib.request
try:
    print(urllib.request.urlopen("http://127.0.0.1:5555/", timeout=5).status)
except urllib.error.HTTPError as e:
    print(e.code)
' 2>/dev/null || echo error)"
if [[ "$GW_STATUS" == "400" ]]; then
  pass "gateway mode answers a request without the public Host with 400 (use tcpSocket probes)"
else
  fail "gateway mode answered '$GW_STATUS' to a request without the public Host (expected 400)"
fi
if docker exec "$GW" test -e /data/data/dashboard-token; then
  fail "gateway mode created a dashboard token file"
else
  pass "gateway mode created no dashboard token file"
fi
if logs_contain "$GW" "$DUMMY_CLAUDE_TOKEN"; then fail "dummy credential appears in gateway-mode logs"; else pass "dummy credential absent from gateway-mode logs"; fi
if logs_contain "$GW" "#token="; then fail "an unlock link appears in gateway-mode logs"; else pass "no unlock link in gateway-mode logs"; fi
HITS="$(grep_files_for "$GW" "$DUMMY_CLAUDE_TOKEN" /data /home/sellbird /tmp)"
if [[ -z "$HITS" ]]; then pass "dummy credential in no file (gateway mode)"; else fail "dummy credential found in: $HITS"; fi

# The same flag without the mode variable must be refused (mode is env-only).
NOGW="${RUN_ID}-nogw"
docker volume create "${NOGW}-data" >/dev/null; VOLUMES+=("${NOGW}-data")
if docker run --rm --name "$NOGW" "${HARDENING[@]}" --network none -v "${NOGW}-data:/data" \
     "$IMAGE" dashboard --host 0.0.0.0 >/dev/null 2>&1; then
  fail "dashboard --host 0.0.0.0 started without SELLBIRD_DASHBOARD_MODE=gateway"
else
  pass "dashboard --host 0.0.0.0 refused without SELLBIRD_DASHBOARD_MODE=gateway"
fi

# ---------------------------------------------------------------------------
if [[ "$BRAIN" == "1" ]]; then
  echo "== brain credential (--brain)"

  # Runs Brain.think once through sellbird.brain with a stand-in `claude` that
  # answers --help with the isolation flags and, for a prompt, returns the
  # SHA-256 of the CLAUDE_CODE_OAUTH_TOKEN it received ("absent" when unset).
  BRAIN_SET_PY='
import asyncio, os, stat, sys
fake_dir = "/tmp/fakebin"
os.makedirs(fake_dir, exist_ok=True)
fake = os.path.join(fake_dir, "claude")
with open(fake, "w") as f:
    f.write("""#!/bin/sh
if [ "$1" = "--help" ]; then
  echo "--safe-mode --setting-sources --no-session-persistence --disable-slash-commands --strict-mcp-config --tools --output-format"
  exit 0
fi
cat >/dev/null
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN+x}" ]; then
  h=$(printf %s "$CLAUDE_CODE_OAUTH_TOKEN" | sha256sum | cut -d" " -f1)
else
  h=absent
fi
printf "{\\"type\\":\\"result\\",\\"result\\":\\"%s\\"}" "$h"
""")
os.chmod(fake, stat.S_IRWXU)
os.environ["PATH"] = fake_dir + os.pathsep + os.environ["PATH"]
from sellbird.brain import Brain
from sellbird.state import StateManager
async def main():
    state = StateManager("/tmp/brain-check.db")
    await state.init_db()
    reply = await Brain(state).think("boundary check", agent="boundary", task="check", max_retries=0)
    print("BRAIN_REPLY=" + reply)
asyncio.run(main())
'
  BS="${RUN_ID}-brain-set"
  docker volume create "${BS}-data" >/dev/null; VOLUMES+=("${BS}-data")
  OUT="$(docker run --name "$BS" "${HARDENING[@]}" --network none -v "${BS}-data:/data" \
           -e CLAUDE_CODE_OAUTH_TOKEN="$DUMMY_CLAUDE_TOKEN" \
           --entrypoint python "$IMAGE" -c "$BRAIN_SET_PY" 2>&1 || true)"
  CONTAINERS+=("$BS")
  if grep -qx "BRAIN_REPLY=$DUMMY_CLAUDE_SHA256" <<<"$OUT"; then
    pass "claude subprocess received CLAUDE_CODE_OAUTH_TOKEN from the brain"
  else
    fail "claude subprocess did not receive the token (reply: $(grep '^BRAIN_REPLY=' <<<"$OUT" || echo none))"
  fi
  if grep -qF -- "$DUMMY_CLAUDE_TOKEN" <<<"$OUT" || logs_contain "$BS" "$DUMMY_CLAUDE_TOKEN"; then
    fail "dummy credential appears in brain output"
  else
    pass "dummy credential absent from brain output"
  fi

  # Unset: the real pinned CLI, no network, the image's empty config directory.
  BRAIN_UNSET_PY='
import asyncio, logging, os, sys
assert "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
from sellbird.brain import Brain
from sellbird.state import StateManager
async def main():
    state = StateManager("/tmp/brain-check.db")
    await state.init_db()
    reply = await Brain(state).think("boundary check", agent="boundary", task="check", max_retries=0)
    print("BRAIN_REPLY_EMPTY=" + str(reply == ""))
    conf = os.environ.get("CLAUDE_CONFIG_DIR", "")
    found = [os.path.join(d, f) for base in ("/data", os.path.expanduser("~"), conf) if base
             for d, _, files in os.walk(base) for f in files if f == ".credentials.json"]
    print("CREDENTIAL_FILES=" + str(len(found)))
asyncio.run(main())
'
  BU="${RUN_ID}-brain-unset"
  docker volume create "${BU}-data" >/dev/null; VOLUMES+=("${BU}-data")
  OUT="$(docker run --name "$BU" "${HARDENING[@]}" --network none -v "${BU}-data:/data" \
           --entrypoint python "$IMAGE" -c "$BRAIN_UNSET_PY" 2>&1 || true)"
  CONTAINERS+=("$BU")
  if grep -qF "Non-retryable Claude error (auth)" <<<"$OUT" && grep -qx "BRAIN_REPLY_EMPTY=True" <<<"$OUT"; then
    pass "unset token: brain reports the documented missing-login error"
  else
    fail "unset token: documented missing-login error not reported"
    echo "      brain output (last lines):"; tail -n 15 <<<"$OUT" | sed 's/^/      /'
  fi
  if grep -qx "CREDENTIAL_FILES=0" <<<"$OUT"; then
    pass "unset token: no credential file to fall back to"
  else
    fail "unset token: a credential file exists ($(grep '^CREDENTIAL_FILES=' <<<"$OUT" || echo unknown))"
  fi
fi

# ---------------------------------------------------------------------------
echo
if (( FAILURES == 0 )); then
  echo "check_container: all checks passed"
  exit 0
fi
echo "check_container: $FAILURES check(s) failed"
exit 1
