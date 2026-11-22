#!/usr/bin/env bash
# Not in the contract's packet: turns results.jsonl into boundary-results.json (one object per
# scenario and control, the last verdict wins) and a README.md skeleton with the commit, base,
# fixture SHA-256 and the table, in the evidence folder. Run it after redaction-grep.sh passes.
set -euo pipefail
# shellcheck source=scripts/boundary/golive/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
golive_begin support SUMMARY
GOLIVE_TREE_BEFORE=""
res="$EVIDENCE_DIR/results.jsonl"
if [ ! -s "$res" ]; then
  golive_finish BLOCKED "no results.jsonl in the evidence folder"
fi
jq -s 'group_by([.scenario, .kind]) | map(last)' "$res" > "$EVIDENCE_DIR/boundary-results.json"
readme="$EVIDENCE_DIR/README.md"
if [ -e "$readme" ]; then
  readme="$(golive_artifact README.md)"
fi
{
  echo "# Boundary run evidence"
  echo
  if [ -f "$EVIDENCE_DIR/run-info.json" ]; then
    echo "- commit: $(jq -r .commit "$EVIDENCE_DIR/run-info.json")"
    echo "- base: $(jq -r .base "$EVIDENCE_DIR/run-info.json")"
    echo "- required-tests fixture SHA-256: $(jq -r .fixture_sha256 "$EVIDENCE_DIR/run-info.json")"
  fi
  echo
  echo "| scenario | kind | status | message |"
  echo "|---|---|---|---|"
  jq -r '.[] | "| \(.scenario) | \(.kind) | \(.status) | \(.message | gsub("\\|"; "/")) |"' "$EVIDENCE_DIR/boundary-results.json"
} > "$readme"
golive_finish PASS "wrote boundary-results.json and $(basename "$readme")"
