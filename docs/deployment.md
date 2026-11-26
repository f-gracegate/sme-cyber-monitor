# Deployment notes

Production infrastructure is Phase 7 work. These rules already apply to any non-development
environment.

## Required configuration (backend)

| Variable | Rule |
| --- | --- |
| `ENVIRONMENT` | `staging` or `production` (anything other than development/test enables strict checks) |
| `SECRET_KEY` | Random, at least 32 characters. The app refuses to start otherwise. |
| `DATA_ENCRYPTION_KEY` | Fernet key, stored in a secret manager, separate from database backups |
| `COOKIE_SECURE` | `true` (HTTPS only) |
| `DATABASE_URL` | The least-privileged `smecm_app` role, never the owner |
| `MIGRATION_DATABASE_URL` | Owner role, used only by `alembic upgrade head` |
| `SEED_ADMIN_PASSWORD` | Strong value from the secret store. The seed refuses weak passwords outside development, and the admin must change it at first sign-in. |
| `FORWARDED_ALLOW_IPS` | Only the reverse proxy / load balancer address(es) |
| `WEB_BASE_URL` | Public HTTPS URL of the web app (used in emails) |

API docs (`/api/docs`) and the developer mailbox are disabled outside development.

## Client IP addresses

Rate limiting and audit logs need the real client IP. Put a reverse proxy or load balancer in
front of the web app that **overwrites** `X-Forwarded-For` with the connecting client address
(not appends a client-supplied one). Set `FORWARDED_ALLOW_IPS` on the backend to that proxy only.
Without this, every request appears to come from the web tier. Sign-in stays protected by
per-account limits and lockout, but per-IP limits become shared.

## Hosting and data residency

Choose the provider and region only after reviewing data residency, contracts, costs, backup
locations and Ghanaian requirements (Data Protection Act 2012, Act 843; Cybersecurity Act 2020,
Act 1038 for managed services). Prefer managed PostgreSQL with encrypted, tested backups.
