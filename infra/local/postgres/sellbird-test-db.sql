-- A second Sellbird database for the boundary's storage test suite.
--
-- Same owner, grants and role settings as `sellbird` in
-- infra/postgres/provision.sql (which has already created both roles). The
-- storage tests drop and recreate Sellbird's schema in the database their DSNs
-- name, so they get this one and the running stand-in keeps `sellbird`.
-- scripts/local/dsn.sh prints DSNs for this database.

\set ON_ERROR_STOP on

CREATE DATABASE sellbird_test OWNER sellbird_migrate ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE sellbird_test FROM PUBLIC;
GRANT CONNECT ON DATABASE sellbird_test TO sellbird_app;

\connect sellbird_test
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO sellbird_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sellbird_migrate IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sellbird_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sellbird_migrate IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO sellbird_app;
ALTER DEFAULT PRIVILEGES FOR ROLE sellbird_migrate IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO sellbird_app;
ALTER ROLE sellbird_app IN DATABASE sellbird_test SET statement_timeout = '30s';
ALTER ROLE sellbird_app IN DATABASE sellbird_test SET idle_in_transaction_session_timeout = '60s';
