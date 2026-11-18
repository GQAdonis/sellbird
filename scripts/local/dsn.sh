#!/usr/bin/env bash
# Print a Sellbird Postgres DSN for the local stand-in, from infra/local/.env.
#
#   scripts/local/dsn.sh migrate            # sellbird_migrate @ sellbird_test
#   scripts/local/dsn.sh app                # sellbird_app     @ sellbird_test
#   scripts/local/dsn.sh migrate sellbird   # the database the running stand-in uses
#
# The default database is `sellbird_test` (provisioned exactly like `sellbird`
# by infra/local/postgres/), because the storage test suite drops and recreates
# Sellbird's schema in the database it is given; pointing it at `sellbird` would
# pull the schema out from under the running container. Meant for command
# substitution, e.g.
#
#   SELLBIRD_TEST_PG_MIGRATE_DSN=$(scripts/local/dsn.sh migrate) \
#   SELLBIRD_TEST_PG_APP_DSN=$(scripts/local/dsn.sh app) .venv/bin/python -m pytest -q -rs
#
# The DSN contains a password: never paste or log it. Postgres is published on
# 127.0.0.1 only, without TLS, hence sslmode=disable (the hosted contract
# requires sslmode=require or stronger).
set -euo pipefail
# shellcheck source=scripts/local/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

role="${1:-}"
db="${2:-sellbird_test}"
case "$role" in
  migrate) user=sellbird_migrate; pw_key=SELLBIRD_MIGRATE_PASSWORD ;;
  app)     user=sellbird_app;     pw_key=SELLBIRD_APP_PASSWORD ;;
  *)       sb_die "usage: dsn.sh migrate|app [sellbird_test|sellbird]" ;;
esac
case "$db" in
  sellbird_test|sellbird) ;;
  *) sb_die "database must be sellbird_test or sellbird" ;;
esac

password="$(sb_env_get "$pw_key")"
port="$(sb_env_get SELLBIRD_LOCAL_PG_PORT)"
printf 'postgresql://%s:%s@127.0.0.1:%s/%s?sslmode=disable&application_name=sellbird-tests\n' \
  "$user" "$password" "$port" "$db"
