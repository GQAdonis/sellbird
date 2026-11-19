-- Databases the platform owns in a hosted deployment, recreated for the local
-- stand-in only: Kratos's and flint-gate's. Each service owns its database so
-- it can run its own migrations; neither role can reach Sellbird's databases
-- (CONNECT on `sellbird` and `sellbird_test` is revoked from PUBLIC).

\set ON_ERROR_STOP on

CREATE ROLE kratos LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
  NOBYPASSRLS PASSWORD :'kratos_password';
CREATE DATABASE kratos OWNER kratos ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE kratos FROM PUBLIC;

CREATE ROLE flintgate LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
  NOBYPASSRLS PASSWORD :'flintgate_password';
CREATE DATABASE flintgate OWNER flintgate ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE flintgate FROM PUBLIC;
