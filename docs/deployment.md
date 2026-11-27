# Deployment notes

The production stack and runbook are in [operations.md](operations.md)
(`deploy/docker-compose.prod.yml`). These rules apply to any non-development environment.

## Required configuration (backend)

| Variable | Rule |
| --- | --- |
| `ENVIRONMENT` | Defaults to `production`. Anything other than `development`/`test` enables the strict checks |
| `SECRET_KEY` | Random, at least 32 characters. The app refuses to start otherwise. |
| `DATA_ENCRYPTION_KEY` | Fernet key, stored in a secret manager, separate from database backups |
| `COOKIE_SECURE` | `true` (HTTPS only) |
| `DATABASE_URL` | The least-privileged `smecm_app` role, never the owner |
| `MIGRATION_DATABASE_URL` | Owner role, used only by `alembic upgrade head` |
| `SEED_ADMIN_PASSWORD` | Strong value from the secret store. The seed refuses weak passwords outside development, and the admin must change it at first sign-in. |
| `FORWARDED_ALLOW_IPS` | Only the reverse proxy / load balancer address(es) |
| `WEB_BASE_URL` | Public HTTPS URL of the web app (used in emails) |
| `AGENT_DIST_PATH` | Path to `smecm_agent.py` inside the backend container (copy `agents/` into the image) |
| `PAYMENT_PROVIDER` | `paystack`. `sandbox` is refused outside development. |
| `PAYSTACK_SECRET_KEY` | Live secret key from the secret store. It also verifies webhook signatures. Set the webhook URL to `https://<api>/api/v1/billing/webhooks/paystack`. |
| `BILLING_GRACE_DAYS`, `ANNUAL_MONTHS_CHARGED` | Defaults 7 and 10 |
| `BILLING_CONTACT_EMAIL` | Where Enterprise enquiries go |
| `PUSH_PROVIDER` | `fcm` in production (`log` keeps pushes in the development outbox) |
| `FCM_SERVICE_ACCOUNT_FILE`, `FCM_PROJECT_ID` | Firebase service-account key (mounted as a secret file) and project |
| `PUSH_INCLUDE_DETAILS` | Leave `false` so lock screens show only severity and title |
| `MOBILE_REFRESH_TOKEN_TTL_DAYS` | Default 30 |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | Required: invitations, resets, verification and alerts are emailed over SMTP with STARTTLS |
| `LOG_FORMAT`, `LOG_ACCESS` | `json` and `true` in production (one JSON line per request, with request ID) |
| `METRICS_TOKEN` | Enables `/api/metrics` for your monitoring system |
| `EVIDENCE_QUOTA_BYTES` | Evidence storage per organisation (default 2 GB) |

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
