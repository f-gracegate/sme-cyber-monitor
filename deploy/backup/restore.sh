#!/usr/bin/env bash
# Restore a backup into an EMPTY database and object directory.
#
#   restore.sh <stamp>      e.g. 20261127T020000Z (default: the newest manifest)
#
#   PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE   the target (owner role; database must exist)
#   APP_DB_USER                                  application role to grant (default smecm_app)
#   BACKUP_PASSPHRASE_FILE BACKUP_DIR OBJECTS_DIR as for backup.sh
set -euo pipefail

: "${PGDATABASE:?}" "${BACKUP_PASSPHRASE_FILE:?}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
OBJECTS_DIR="${OBJECTS_DIR:-/data/objects}"
APP_DB_USER="${APP_DB_USER:-smecm_app}"
stamp="${1:-$(ls -1 "$BACKUP_DIR"/manifest-*.txt | sort | tail -1 | sed 's/.*manifest-\(.*\)\.txt/\1/')}"
manifest="$BACKUP_DIR/manifest-$stamp.txt"
[ -f "$manifest" ] || { echo "no backup $stamp" >&2; exit 1; }

echo "verifying checksums for $stamp"
(cd "$BACKUP_DIR" && grep -E '\.gpg$' "$manifest" | sha256sum -c -)

decrypt() {
  gpg --batch --quiet --decrypt --passphrase-file "$BACKUP_PASSPHRASE_FILE" "$1"
}

if [ "$(psql -At -c "SELECT count(*) FROM pg_tables WHERE schemaname='public'")" != "0" ]; then
  echo "target database is not empty; refusing to restore over existing data" >&2
  exit 1
fi

decrypt "$BACKUP_DIR/db-$stamp.dump.gpg" \
  | pg_restore --exit-on-error --no-owner --no-privileges --dbname "$PGDATABASE"

# The dump leaves out grants: give the application role exactly what it has in production.
psql -v ON_ERROR_STOP=1 -q <<SQL
GRANT USAGE ON SCHEMA public TO ${APP_DB_USER};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ${APP_DB_USER};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ${APP_DB_USER};
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs, incident_events FROM ${APP_DB_USER};
REVOKE DELETE, TRUNCATE ON payments FROM ${APP_DB_USER};
REVOKE TRUNCATE ON feedback, suppression_rules, data_exports FROM ${APP_DB_USER};
SQL

mkdir -p "$OBJECTS_DIR"
decrypt "$BACKUP_DIR/objects-$stamp.tar.gpg" | tar -C "$OBJECTS_DIR" -xf -
echo "restore $stamp complete"
