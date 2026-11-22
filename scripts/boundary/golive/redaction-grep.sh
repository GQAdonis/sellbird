#!/usr/bin/env bash
# Supplementary redaction check over the evidence folder (packet: `redaction`). Searches every text
# file for secret, token, connection-string and email-address patterns and mail-server host names.
# ANY hit is a FAIL listing `label file:line` only; the matched text is never printed or stored.
# Allowed email domains: example.com/.org/.net and *.test, *.invalid, *.example, *.localhost.
# The blocking personal-data check is a read of the full phase diff at the cumulative review.
#   bash scripts/boundary/golive/redaction-grep.sh SCN-LIVE-001,SCN-LIVE-002,SCN-LIVE-003,SCN-SHIP-002
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin scenario SCN-LIVE-001,SCN-LIVE-002,SCN-LIVE-003,SCN-SHIP-002
GOLIVE_TREE_BEFORE=""
cd "$GOLIVE_ROOT"

hits=0
# scan LABEL ERE: list file:line for every match (grep -n, line number kept, text cut off at once).
scan() {
  local label="$1" re="$2" out
  out="$(grep -rInE -e "$re" "$EVIDENCE_DIR" 2> /dev/null | awk -F: '{print $1 ":" $2}' | sort -u || true)"
  if [ -n "$out" ]; then
    while IFS= read -r loc; do
      printf 'HIT %s %s\n' "$label" "${loc#"$EVIDENCE_DIR"/}"
      hits=$((hits + 1))
    done <<< "$out"
  fi
}
# scan_email LABEL ERE ALLOWED_TAIL_ERE: like scan, but drops matches whose text ends in an allowed domain.
scan_email() {
  local label="$1" re="$2" allow="$3" out
  out="$(grep -rInoE -e "$re" "$EVIDENCE_DIR" 2> /dev/null | grep -vE -e "$allow" | awk -F: '{print $1 ":" $2}' | sort -u || true)"
  if [ -n "$out" ]; then
    while IFS= read -r loc; do
      printf 'HIT %s %s\n' "$label" "${loc#"$EVIDENCE_DIR"/}"
      hits=$((hits + 1))
    done <<< "$out"
  fi
}

scan github-token 'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}'
scan api-key 'sk-(ant-)?[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}'
scan private-key '-----BEGIN [A-Z ]*PRIVATE KEY-----'
scan jwt 'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'
scan dsn-with-credentials '[A-Za-z][A-Za-z0-9+.-]*://[^/@[:space:]:]+:[^@/[:space:]]+@'
scan env-secret '(PASSWORD|SECRET|TOKEN|API_KEY|APIKEY|PRIVATE_KEY)[A-Z_]*=[^[:space:]*]{6,}'
scan session-cookie 'ory_kratos_session=[A-Za-z0-9._~+/=-]{10,}'
scan bearer '[Bb]earer [A-Za-z0-9._~+/=-]{20,}'
scan_email email-address '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' \
  '@(example\.(com|org|net)|[A-Za-z0-9.-]+\.(test|invalid|example|localhost))$'
scan_email mail-host '(smtp|imap|mail|mx)[0-9]*\.[A-Za-z0-9.-]+\.[A-Za-z]{2,}' \
  '(example\.(com|org|net)|[A-Za-z0-9.-]+\.(test|invalid|example|localhost))$'

nfiles="$(find "$EVIDENCE_DIR" -type f | wc -l | tr -d ' ')"
golive_note "scanned $nfiles files, $hits hit(s)"
if [ "$hits" -gt 0 ]; then
  golive_finish FAIL "$hits redaction hit(s) in the evidence folder (labels and file:line above); stop the run, do not publish the evidence"
fi
golive_finish PASS "no secret, token, connection-string, email-address or mail-host pattern in $nfiles evidence files"
