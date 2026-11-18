-- Sellbird's database and roles on a Postgres 18 server (flint-forge image).
--
-- This is the provisioning in docs/platform-interface.md ("Database
-- provisioning"), statement for statement. In the shared cluster the platform
-- runs it once; use this file for a local or test server. Run it as a
-- superuser with psql, passing the two passwords as variables (never commit
-- them, never put them on a shared command line history):
--
--   psql "$SUPERUSER_URL" -v ON_ERROR_STOP=1 \
--        -v migrate_password="$SELLBIRD_MIGRATE_PASSWORD" \
--        -v app_password="$SELLBIRD_APP_PASSWORD" \
--        -f infra/postgres/provision.sql
--
-- Then apply the schema as the migration role:
--
--   SELLBIRD_MIGRATE_DATABASE_URL=postgresql://sellbird_migrate:...@host:5432/sellbird \
--     sellbird storage migrate
--
-- and run Sellbird as the runtime role (SELLBIRD_DATABASE_URL with
-- sellbird_app). The runtime role reads and writes rows and nothing else.
-- Row-level security is not used: one workspace per database (ADR 0001).
-- No extension is needed or created.

\set ON_ERROR_STOP on

CREATE ROLE sellbird_migrate LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD :'migrate_password';
CREATE ROLE sellbird_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 20 PASSWORD :'app_password';
CREATE DATABASE sellbird OWNER sellbird_migrate ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE sellbird FROM PUBLIC;
GRANT CONNECT ON DATABASE sellbird TO sellbird_app;

\connect sellbird
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO sellbird_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sellbird_migrate IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sellbird_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sellbird_migrate IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO sellbird_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sellbird_migrate IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO sellbird_app;
ALTER ROLE sellbird_app IN DATABASE sellbird SET statement_timeout = '30s';
ALTER ROLE sellbird_app IN DATABASE sellbird SET idle_in_transaction_session_timeout = '60s';
