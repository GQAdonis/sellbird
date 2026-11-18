#!/usr/bin/env bash
# First-init provisioning for the local stand-in's Postgres 18 (flint-forge image).
#
# Mounted into /docker-entrypoint-initdb.d/ beside the image's own 01/02/99
# scripts, so it runs exactly once, when the data volume is created
# (scripts/local/make-env.sh always starts from a fresh volume). It runs as the
# image's superuser over the local socket and applies:
#
#   1. infra/postgres/provision.sql, unmodified: roles sellbird_migrate and
#      sellbird_app, database `sellbird`, the contract's grants and settings;
#   2. sellbird-test-db.sql: database `sellbird_test` with the same owner and
#      grants, for the boundary's storage test suite (which drops and recreates
#      Sellbird's schema, so it must not share a database with the running app);
#   3. platform-dbs.sql: the `kratos` and `flintgate` roles and databases that
#      the platform would own in a hosted deployment.
#
# Passwords come from the container's environment (from the uncommitted .env).
set -euo pipefail

: "${SELLBIRD_MIGRATE_PASSWORD:?}" "${SELLBIRD_APP_PASSWORD:?}"
: "${KRATOS_DB_PASSWORD:?}" "${FLINTGATE_DB_PASSWORD:?}"

run_sql() {
  psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$POSTGRES_USER" \
       --dbname "$POSTGRES_DB" "$@"
}

run_sql -v migrate_password="$SELLBIRD_MIGRATE_PASSWORD" \
        -v app_password="$SELLBIRD_APP_PASSWORD" \
        -f /sellbird-local/provision.sql
run_sql -f /sellbird-local/sellbird-test-db.sql
run_sql -v kratos_password="$KRATOS_DB_PASSWORD" \
        -v flintgate_password="$FLINTGATE_DB_PASSWORD" \
        -f /sellbird-local/platform-dbs.sql
echo "sellbird-local: provisioning complete"
