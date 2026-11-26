#!/bin/sh
# Creates the least-privileged application role and the test database.
# Runs once, when the Postgres data volume is first initialised.
#
# The owner role (POSTGRES_USER) runs migrations only. The application connects
# as APP_DB_USER, which owns no tables, so PostgreSQL Row-Level Security applies to it.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE ROLE ${APP_DB_USER} LOGIN PASSWORD '${APP_DB_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  CREATE DATABASE ${POSTGRES_DB}_test OWNER ${POSTGRES_USER};
EOSQL

for db in "$POSTGRES_DB" "${POSTGRES_DB}_test"; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<-EOSQL
    REVOKE ALL ON SCHEMA public FROM PUBLIC;
    GRANT CONNECT ON DATABASE ${db} TO ${APP_DB_USER};
    GRANT USAGE ON SCHEMA public TO ${APP_DB_USER};
    ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${APP_DB_USER};
    ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
      GRANT USAGE, SELECT ON SEQUENCES TO ${APP_DB_USER};
EOSQL
done
