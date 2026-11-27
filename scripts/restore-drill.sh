#!/usr/bin/env bash
# Back up the local stack, restore into a clean server and verify (security scenario 10).
#   scripts/restore-drill.sh
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose -f docker-compose.yml -f deploy/drill.compose.yml --profile drill)

echo "== starting the stack"
"${compose[@]}" up -d --build --wait postgres redis backend

echo "== making sure there is an encrypted object to back up"
"${compose[@]}" exec -T backend python - <<'PY'
from sqlalchemy import select
from app.core.db import SessionLocal
from app.models import Organisation
from app.services import storage
db = SessionLocal(); db.info["rls"] = {"bypass": True}
org = db.scalar(select(Organisation).limit(1))
storage.put(org.id, "reports", b"restore drill sample object")
print("object written for", org.name)
PY

echo "== backing up"
# A fresh random passphrase for this drill; in production it comes from the secret store.
"${compose[@]}" run --rm -T --user root --entrypoint sh backup -c \
  'head -c 48 /dev/urandom | base64 > /drill/passphrase && chmod 600 /drill/passphrase && chown -R postgres /drill /backups'
"${compose[@]}" run --rm -T backup /usr/local/bin/backup.sh

echo "== restoring into a clean server"
"${compose[@]}" up -d --wait postgres-restore
"${compose[@]}" exec -T postgres-restore psql -U smecm_owner -d smecm -v ON_ERROR_STOP=1 \
  -c "CREATE ROLE smecm_app LOGIN PASSWORD 'smecm_app_dev' NOBYPASSRLS"
"${compose[@]}" run --rm -T --user root --entrypoint sh restore -c 'chown -R postgres /restore/objects'
"${compose[@]}" run --rm -T restore /usr/local/bin/restore.sh

echo "== verifying"
manifest=$("${compose[@]}" run --rm -T --entrypoint sh restore -c 'ls -1 /backups/manifest-*.txt | sort | tail -1')
"${compose[@]}" run --rm -T --user root \
  -v sme-cyber-monitor_drill-backups:/backups:ro \
  -v sme-cyber-monitor_drill-objects:/restore/objects:ro \
  -e RESTORE_DATABASE_URL=postgresql+psycopg://smecm_owner:smecm_owner_dev@postgres-restore:5432/smecm \
  -e RESTORE_APP_DATABASE_URL=postgresql+psycopg://smecm_app:smecm_app_dev@postgres-restore:5432/smecm \
  -e MANIFEST="$manifest" -e OBJECTS_DIR=/restore/objects \
  backend python -m app.ops.verify_restore && status=0 || status=$?

"${compose[@]}" rm -sf postgres-restore >/dev/null
exit $status
