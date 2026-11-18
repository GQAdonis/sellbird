#!/usr/bin/env bash
# Check that the platform interface contract document is complete and well-formed.
#
# Usage: scripts/boundary/check_platform_contract.sh docs/platform-interface.md
#
# Asserts every required section heading, the Secret names and keys, the minted
# claims (iss, aud, sub, kid, exp), the JWKS URL shape, the overlay path and pin
# format, and the hostname placeholder; also refuses hostnames, email addresses
# and identity ids that are not placeholders. Prints one line per missing or
# malformed item and exits 1 if there is any, 0 if the document passes, 2 on a
# usage error.
#
# The required-section list mirrors the "Required contract sections" requirement
# in openspec/changes/platform-interface-contract/specs/platform-interface/spec.md.
# A passing check does not mean the contract is agreed: agreement is an operator
# decision recorded in the KBD decision log.
#
# Portable to bash 3.2 (macOS) and GNU/BSD grep and awk; reads the document only.

set -u

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <path-to-platform-interface.md>" >&2
  exit 2
fi

DOC=$1
if [ ! -f "$DOC" ] || [ ! -r "$DOC" ]; then
  echo "error: cannot read $DOC" >&2
  exit 2
fi

failures=0
checks=0

fail() {
  echo "MISSING: $1"
  failures=$((failures + 1))
}

# Print the body of section "## <name>" (up to the next "## " heading).
section_body() {
  awk -v h="## $1" '
    $0 == h { found = 1; next }
    found && /^## / { exit }
    found { print }
  ' "$DOC"
}

has_section() {
  grep -Fxq "## $1" "$DOC"
}

# req_lit <section> <literal> <label>: the section contains the literal text.
req_lit() {
  checks=$((checks + 1))
  if ! section_body "$1" | grep -Fq -- "$2"; then
    fail "$3 (section '$1')"
  fi
}

# req_re <section> <extended-regex> <label>: some line in the section matches.
req_re() {
  checks=$((checks + 1))
  if ! section_body "$1" | grep -Eq -- "$2"; then
    fail "$3 (section '$1')"
  fi
}

# req_row <section> <first-cell-regex> <literal-in-row> <label>: a table row whose
# first cell matches also contains the literal.
req_row() {
  checks=$((checks + 1))
  if ! section_body "$1" | grep -E -- "^[|] $2 [|]" | grep -Fq -- "$3"; then
    fail "$4 (section '$1')"
  fi
}

# forbid_re <section> <extended-regex> <label>: no line in the section matches.
forbid_re() {
  checks=$((checks + 1))
  if section_body "$1" | grep -Eq -- "$2"; then
    fail "$3 (section '$1')"
  fi
}

REQUIRED_SECTIONS="Status and agreement
Ownership summary
Namespaces
Database provisioning
Identity (Kratos)
Operator identity provisioning
Gateway (flint-gate)
Issuer and JWKS
Minted claims
Route ownership
Hostname and certificate
Session cookie domain
Secrets
AI credential
Gateway configuration values
Overlay location and pin format
Argo CD ownership
Migration flow
NetworkPolicy
Rotation and revocation
Out of scope
Placeholders"

# 1. Required section headings. A missing section is reported by name and its
#    item checks are skipped, so the report names the section rather than every
#    item inside it.
present=""
OLDIFS=$IFS
IFS='
'
for s in $REQUIRED_SECTIONS; do
  checks=$((checks + 1))
  if has_section "$s"; then
    present="$present|$s|"
  else
    fail "section '$s'"
  fi
done
IFS=$OLDIFS

is_present() {
  case "$present" in
    *"|$1|"*) return 0 ;;
    *) return 1 ;;
  esac
}

# 2. Items inside each section.
S="Status and agreement"
if is_present "$S"; then
  req_re "$S" 'Contract version: `[0-9]+`' "contract version number"
  req_lit "$S" "agreement decision" "operator agreement rule"
fi

S="Namespaces"
if is_present "$S"; then
  for ns in sellbird flint-gate flint-forge argocd; do
    req_re "$S" "^[|] \`$ns\` [|]" "namespace '$ns'"
  done
  req_lit "$S" "app.kubernetes.io/name: flint-gate" "flint-gate pod label"
  req_lit "$S" "app.kubernetes.io/name: flint-forge-postgres" "Postgres pod label"
fi

S="Database provisioning"
if is_present "$S"; then
  req_lit "$S" "CREATE DATABASE sellbird OWNER sellbird_migrate" "database owned by the migration role"
  req_lit "$S" "CREATE ROLE sellbird_migrate" "migration role"
  req_lit "$S" "CREATE ROLE sellbird_app" "runtime role"
  req_lit "$S" "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sellbird_app" "runtime role DML grants"
  req_lit "$S" "REVOKE ALL ON DATABASE sellbird FROM PUBLIC" "database closed to PUBLIC"
  req_lit "$S" "NOSUPERUSER" "roles are not superusers"
  forbid_re "$S" 'GRANT[^;]*(CREATE|ALL)[^;]*TO sellbird_app' "runtime role must have no CREATE or ALL grant"
  req_re "$S" 'postgresql://<role>:<password>@<pg-host>:5432/sellbird\?sslmode=' "connection string shape"
fi

S="Identity (Kratos)"
if is_present "$S"; then
  req_row "$S" '`selfservice\.flows\.registration\.enabled`' '`false`' "registration disabled"
  req_row "$S" '`session\.whoami\.required_aal`' '`highest_available`' "whoami requires the highest available AAL"
  req_lit "$S" "selfservice.methods.totp.enabled" "TOTP second factor"
  req_lit "$S" "aal2" "aal2 requirement"
fi

S="Operator identity provisioning"
if is_present "$S"; then
  req_lit "$S" "/admin/identities" "admin API identity creation"
  req_lit "$S" "SELLBIRD_GATE_ALLOWED_SUBS" "allowlist destination"
fi

S="Gateway (flint-gate)"
if is_present "$S"; then
  req_lit "$S" "kratos_session" "kratos_session provider"
  req_lit "$S" "Authorization: Bearer" "bearer token forwarding"
  req_lit "$S" "x-flint-" "x-flint-* headers ignored"
  req_lit "$S" "cookies" "cookies ignored"
fi

S="Issuer and JWKS"
if is_present "$S"; then
  req_row "$S" 'Signing algorithm' '`RS256`' "RS256 signing algorithm"
  req_row "$S" 'Issuer string \(`iss`\)' '`https://gate.example.test`' "issuer placeholder"
  req_re "$S" '`http://[a-z0-9-]+\.[a-z0-9-]+\.svc\.cluster\.local:[0-9]+/\.well-known/jwks\.json`' "in-cluster JWKS URL"
  req_lit "$S" "/.well-known/jwks.json" "JWKS path"
  req_lit "$S" "jku" "keys never taken from the token header"
fi

S="Minted claims"
if is_present "$S"; then
  for c in iss aud sub kid exp; do
    req_re "$S" "^[|] \`$c\` [|]" "claim '$c'"
  done
  req_row "$S" '`aud`' '`sellbird`' "aud value 'sellbird'"
  req_row "$S" '`sub`' 'Kratos identity id' "sub is the Kratos identity id"
  req_row "$S" '`exp`' '`300`' "TTL of at most 300 seconds"
  req_row "$S" '`alg`' '`RS256`' "alg RS256"
  req_re "$S" '^ *aud: "sellbird"$' "route additional_claims set aud"
fi

S="Route ownership"
if is_present "$S"; then
  req_lit "$S" "infra/flint-gate/sellbird-routes.yaml" "Sellbird route file"
  req_lit "$S" "http://sellbird.sellbird.svc.cluster.local:5555" "Sellbird upstream"
fi

S="Hostname and certificate"
if is_present "$S"; then
  req_lit "$S" "sellbird.example.test" "hostname placeholder"
  req_lit "$S" "Certificate" "certificate ownership"
  req_lit "$S" "listener" "listener ownership"
fi

S="Session cookie domain"
if is_present "$S"; then
  req_lit "$S" "ory_kratos_session" "session cookie name"
  req_row "$S" '`session\.cookie\.same_site`' '`Lax`' "SameSite=Lax"
  req_lit "$S" "example.test" "cookie domain placeholder"
fi

S="Secrets"
if is_present "$S"; then
  req_row "$S" '`sellbird-db-migrate`' '`SELLBIRD_DATABASE_URL`' "Secret sellbird-db-migrate key SELLBIRD_DATABASE_URL"
  req_row "$S" '`sellbird-db-app`' '`SELLBIRD_DATABASE_URL`' "Secret sellbird-db-app key SELLBIRD_DATABASE_URL"
  req_row "$S" '`sellbird-claude`' '`CLAUDE_CODE_OAUTH_TOKEN`' "Secret sellbird-claude key CLAUDE_CODE_OAUTH_TOKEN"
  req_lit "$S" "secretKeyRef" "secrets referenced by name only"
fi

S="AI credential"
if is_present "$S"; then
  req_lit "$S" "sellbird-claude" "AI credential Secret name"
  req_lit "$S" "CLAUDE_CODE_OAUTH_TOKEN" "AI credential key"
  req_lit "$S" "MUST NOT be written to disk" "no file persistence"
  req_lit "$S" "MUST NOT be logged" "no logging"
fi

S="Gateway configuration values"
if is_present "$S"; then
  for k in SELLBIRD_DASHBOARD_MODE SELLBIRD_PUBLIC_HOST SELLBIRD_GATE_ISSUER \
           SELLBIRD_GATE_AUDIENCE SELLBIRD_GATE_JWKS_URL SELLBIRD_GATE_ALLOWED_SUBS; do
    req_re "$S" "^[|] \`$k\` [|]" "config key '$k'"
  done
fi

S="Overlay location and pin format"
if is_present "$S"; then
  req_lit "$S" "SELLBIRD_PLATFORM_REPO" "repository variable naming the platform repo"
  req_lit "$S" "apps/sellbird/overlays/production/kustomization.yaml" "overlay file path"
  req_lit "$S" '^[0-9a-f]{40}$' "newTag format rule"
  req_lit "$S" '^sha256:[0-9a-f]{64}$' "digest format rule"
  req_re "$S" '^ *- name: sellbird$' "images entry for logical name 'sellbird'"
  req_re "$S" '^ *newTag: "[0-9a-f]{40}"$' "well-formed example newTag"
  req_re "$S" '^ *digest: sha256:[0-9a-f]{64}$' "well-formed example digest"
  req_lit "$S" "Never backwards" "never-backwards rule"
fi

S="Argo CD ownership"
if is_present "$S"; then
  req_lit "$S" "AppProject" "AppProject ownership"
  req_lit "$S" "Application" "Application ownership"
  req_lit "$S" "apps/sellbird/overlays/production" "Application source path"
fi

S="Migration flow"
if is_present "$S"; then
  req_lit "$S" "PreSync" "migration Job as a PreSync hook"
  req_lit "$S" "sellbird storage migrate" "migrate command"
  req_lit "$S" "sellbird-db-migrate" "migration Job uses the migration Secret"
fi

S="NetworkPolicy"
if is_present "$S"; then
  req_lit "$S" "default-deny" "default-deny policy"
  req_re "$S" '^[|] ingress [|].*flint-gate.*5555' "ingress only from flint-gate on 5555"
  req_re "$S" '^[|] egress [|].*flint-forge-postgres.*5432' "egress to Postgres on 5432"
  req_lit "$S" "169.254.0.0/16" "metadata range excluded from egress"
fi

S="Rotation and revocation"
if is_present "$S"; then
  req_lit "$S" "300 s" "residual token lifetime"
fi

S="Out of scope"
if is_present "$S"; then
  req_re "$S" '^- ' "at least one out-of-scope item"
fi

S="Placeholders"
if is_present "$S"; then
  req_lit "$S" "sellbird.example.test" "hostname placeholder listed"
fi

# 3. Whole-document checks.
checks=$((checks + 1))
if ! grep -Fq "sellbird.example.test" "$DOC"; then
  fail "hostname placeholder 'sellbird.example.test' (document)"
fi

# Hostnames on common public TLDs must be placeholders or known infrastructure.
checks=$((checks + 1))
bad_hosts=$(grep -oiE '([a-z0-9-]+\.)+(com|net|org|io|tools|dev|app|ai|co|cloud|me|tech|xyz|biz|info)([^a-z0-9.-]|$)' "$DOC" \
  | sed -E 's/[^a-zA-Z0-9.-]$//' | tr 'A-Z' 'a-z' | sort -u \
  | while IFS= read -r host; do
      case "$host" in
        example.com|*.example.com|example.net|*.example.net|example.org|*.example.org) ;;
        ghcr.io|github.com|kubernetes.io|*.kubernetes.io|argoproj.io|*.argoproj.io) ;;
        *) echo "$host" ;;
      esac
    done)
if [ -n "$bad_hosts" ]; then
  for h in $bad_hosts; do
    fail "non-placeholder hostname '$h' must be replaced by an example.test placeholder (document)"
  done
fi

# Email addresses must use reserved example domains.
checks=$((checks + 1))
bad_emails=$(grep -oE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$DOC" | sort -u \
  | while IFS= read -r addr; do
      case "$addr" in
        *@example.com|*@example.net|*@example.org|*@*.example|*@*.test|*@*.invalid) ;;
        *) echo "$addr" ;;
      esac
    done)
if [ -n "$bad_emails" ]; then
  for e in $bad_emails; do
    fail "non-placeholder email address '$e' (document)"
  done
fi

# Identity ids: the only UUID allowed is the documented placeholder.
checks=$((checks + 1))
bad_ids=$(grep -oiE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' "$DOC" | sort -u \
  | grep -vx '00000000-0000-4000-8000-000000000001' || true)
if [ -n "$bad_ids" ]; then
  for u in $bad_ids; do
    fail "non-placeholder identity id '$u' (document)"
  done
fi

if [ "$failures" -gt 0 ]; then
  echo "FAIL: $failures of $checks checks failed in $DOC"
  exit 1
fi

echo "OK: $checks checks passed in $DOC (agreement is an operator decision, not checked here)"
exit 0
