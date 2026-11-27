#!/usr/bin/env bash
# Encrypted backup of the database and the object store (evidence, reports, exports).
#
#   PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE   the database to back up (owner role)
#   BACKUP_PASSPHRASE_FILE                       passphrase for AES-256 (GnuPG), kept apart
#                                                from the backups themselves
#   BACKUP_DIR (default /backups)  OBJECTS_DIR (default /data/objects)
#   BACKUP_KEEP_DAYS (default 30)
#
# Output: db-<stamp>.dump.gpg, objects-<stamp>.tar.gpg and manifest-<stamp>.txt (SHA-256 of
# both files plus row counts, which the restore drill checks).
set -euo pipefail

: "${PGDATABASE:?}" "${BACKUP_PASSPHRASE_FILE:?}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
OBJECTS_DIR="${OBJECTS_DIR:-/data/objects}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
mkdir -p "$BACKUP_DIR"

encrypt() {
  gpg --batch --yes --quiet --symmetric --cipher-algo AES256 \
    --passphrase-file "$BACKUP_PASSPHRASE_FILE" --output "$1"
}

pg_dump --format=custom --no-owner --no-privileges --quote-all-identifiers \
  | encrypt "$BACKUP_DIR/db-$stamp.dump.gpg"
tar -C "$OBJECTS_DIR" -cf - . | encrypt "$BACKUP_DIR/objects-$stamp.tar.gpg"

{
  echo "stamp $stamp"
  (cd "$BACKUP_DIR" && sha256sum "db-$stamp.dump.gpg" "objects-$stamp.tar.gpg")
  psql -At -c "SELECT version_num FROM alembic_version" | sed 's/^/alembic /'
  for t in organisations users assets findings alerts incidents incident_events payments audit_logs; do
    echo "rows $t $(psql -At -c "SELECT count(*) FROM \"$t\"")"
  done
} > "$BACKUP_DIR/manifest-$stamp.txt"

find "$BACKUP_DIR" -maxdepth 1 -type f -mtime "+$KEEP_DAYS" -delete
echo "backup $stamp complete"
