# Operations runbook (Phase 7)

## Deploying (single server, pilot scale)

Any Linux VM with Docker (4 vCPU, 8 GB RAM and 100 GB disk is enough for the pilot). Choose
the provider and region after the data-residency review in [compliance.md](compliance.md).

```bash
git clone https://github.com/f-gracegate/sme-cyber-monitor.git && cd sme-cyber-monitor
cp deploy/.env.production.example deploy/.env.production   # fill in every value
mkdir -p deploy/secrets && chmod 700 deploy/secrets
python3 -c "import secrets; print(secrets.token_urlsafe(48))" > deploy/secrets/backup_passphrase
# Firebase service-account key, if push is on:  deploy/secrets/fcm.json
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.production up -d --build
```

- **Caddy** obtains and renews the TLS certificate for `APP_DOMAIN` automatically. Point DNS at
  the server and open ports 80 and 443 only.
- **Hardening:** every application container runs read-only, without root, with all Linux
  capabilities dropped and `no-new-privileges`. Postgres and Redis (password-protected) have no
  published ports.
- **Migrations** run automatically when the backend starts. The first platform administrator
  is seeded from `SEED_ADMIN_*` and must change the password at first sign-in.
- **Updates:** `git pull && docker compose ... up -d --build`. Take a backup first.
- **Paystack webhook:** `https://<APP_DOMAIN>/api/v1/billing/webhooks/paystack`.

Store `DATA_ENCRYPTION_KEY` and the backup passphrase in a password manager or secret store
**outside** the server. Without them, backups and stored files can't be read.

## Backups

- **Schedule:** the `backup` service runs nightly at 02:00 UTC. It saves an encrypted database
  dump (`pg_dump`, AES-256 via GnuPG), an encrypted archive of the object store (evidence,
  reports, exports; already Fernet-encrypted) and a manifest with SHA-256 checksums and row
  counts. It keeps 30 days.
- **Off-site copy:** copy `deploy/backups/` off the server every day, for example
  `rclone copy deploy/backups remote:smecm-backups` to object storage with versioning and
  object lock (immutable). Ransomware on the server must not be able to delete the copies.
- **On demand:**
  `docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.production exec backup /usr/local/bin/backup.sh`.

## Restoring

1. Create a new server (or a new `pgdata` volume) and start only `postgres`.
2. Create the application role:
   `CREATE ROLE smecm_app LOGIN PASSWORD '<APP_DB_PASSWORD>' NOBYPASSRLS;`.
3. Copy the backup files into `deploy/backups/` and run
   `docker compose ... run --rm backup /usr/local/bin/restore.sh <stamp>`. It checks the
   checksums, refuses to overwrite a non-empty database, restores, re-applies the
   least-privilege grants and restores the object store.
4. Start the rest of the stack with the **same** `DATA_ENCRYPTION_KEY`.

The restore role must be able to bypass RLS (the Postgres superuser in this stack). On a
managed database, use a role with `BYPASSRLS` for the restore only.

**Restore drill (security scenario 10):** `scripts/restore-drill.sh` backs up the development
stack, restores into a brand-new database server and verifies the result:
- the schema version
- row counts match the manifest
- RLS is forced on every tenant table
- the app role sees nothing without a tenant context
- append-only tables are intact
- every object decrypts

CI runs it on every push. Also run it against a copy of production once a quarter, and record
the date.

## Monitoring the platform

| Signal | Where | Alert when |
| --- | --- | --- |
| Health | `GET /api/health` (database, redis, worker) | not `ok` for 2 minutes |
| Metrics | `GET http://backend:8000/api/metrics` with `Authorization: Bearer $METRICS_TOKEN` (Prometheus; Caddy blocks it from the internet) | see below |
| `smecm_worker_heartbeat_age_seconds` | monitor workers | > 120 |
| `smecm_checks_overdue` | scheduled checks more than 5 min late | > 50 for 10 minutes |
| `smecm_push_backlog` | notifications waiting to be pushed | > 100 |
| `smecm_http_request_duration_ms` | API latency histogram per route | p95 > 500 ms |
| `smecm_http_requests_total{status=~"5.."}` | server errors | any sustained rate |
| Logs | JSON lines on stdout (`LOG_FORMAT=json`), with `request_id` on every line | `BACKUP FAILED`, `ERROR` |

Use any collector (Grafana Cloud, Better Stack or Uptime Kuma for a start). An external uptime
check on `https://<APP_DOMAIN>/api/health` every minute covers the 99.5% availability target.

## Key rotation

| Secret | How | Effect |
| --- | --- | --- |
| `SECRET_KEY` | Replace and restart | Access tokens stop working; web and mobile clients refresh automatically, so most people won't notice. Email-verification links and sign-ins halfway through MFA must be redone |
| Database and Redis passwords | `ALTER ROLE ... PASSWORD`, update `.env.production`, restart | None |
| `PAYSTACK_SECRET_KEY`, SMTP, FCM | Rotate at the provider, update and restart | None |
| `METRICS_TOKEN` | Update here and in the collector | None |
| `DATA_ENCRYPTION_KEY` | Needs a re-encryption job (not yet built). Treat as long-lived and protect accordingly | — |
| Backup passphrase | New file; keep the old one for older backups | None |

## If the platform itself is attacked

1. **Contain:** restrict access (Caddy `respond 503` or the firewall), revoke suspicious
   sessions (`UPDATE auth_sessions SET revoked_at = now()`), and rotate exposed secrets.
2. **Preserve:** snapshot the server and keep logs and the latest backup unmodified.
3. **Assess:** use the audit log (`audit_logs`, append-only) and the request IDs in the logs.
4. **Notify:**
   - Affected customers without delay.
   - The Data Protection Commission where personal data is affected.
   - The Cyber Security Authority, as Act 1038 requires.
   See [compliance.md](compliance.md).
5. **Recover** from a clean build and the last good backup. Then review what happened.

## Erasure and retention jobs

The monitor worker applies each organisation's telemetry retention hourly, expires data exports
after 7 days, and erases organisations whose 30-day deletion cooling-off has ended. Erasure
uses the database owner role, because the application role can't delete the append-only
incident timeline. Each erasure is recorded as `organisation.erased` in the audit log.
