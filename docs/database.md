# Database

PostgreSQL is the system of record. Migrations live in `backend/migrations/versions` and run as
the owner role; the application uses the least-privileged `smecm_app` role
(`infrastructure/database/init/01-roles.sh`).

## Tables (Milestone 1)

| Table | Purpose | Tenant scoped | RLS |
| --- | --- | --- | --- |
| `users` | People who can sign in (global) | — | — |
| `auth_sessions` | Signed-in devices; hashed rotating refresh token | — | — |
| `password_reset_tokens` | Hashed single-use reset tokens | — | — |
| `organisations` | Customer businesses (the tenant) | self | ✅ |
| `memberships` | User ↔ organisation with one role | ✅ | ✅ |
| `departments` | Teams inside an organisation | ✅ | ✅ |
| `invitations` | Hashed single-use invitation tokens | ✅ | ✅ |
| `assets` | Websites, devices, servers, network and cloud assets | ✅ | ✅ |
| `asset_authorisations` | Proof of control or permission to monitor | ✅ | ✅ |
| `subscriptions` | Plan, status and period per organisation | ✅ | ✅ |
| `audit_logs` | Append-only record of security-relevant actions | ✅ | ✅ |

`audit_logs` grants the application `INSERT` and `SELECT` only. `UPDATE`, `DELETE` and `TRUNCATE`
are revoked, and a test asserts it.

## Planned (later phases)

`agents`, `agent_enrolment_tokens`, `collectors`, `monitoring_profiles`, `monitoring_checks`,
`check_runs`, `findings`, `finding_evidence`, `alerts`, `incidents`, `incident_events`,
`remediation_tasks`, `notifications`, `reports`, `usage_records`, `detection_rules`,
`event_envelopes`, `event_sources`, `api_keys`, `integration_connections`, `alert_rules`,
`risk_score_history`, `data_retention_policies`, `asset_discovery_jobs`.

High-volume raw telemetry will go to an indexed event store (OpenSearch evaluation), not
ordinary relational tables. PostgreSQL keeps the authoritative business records.

## Secrets at rest

Passwords and recovery codes: Argon2id. Refresh, reset and invitation tokens: SHA-256 (they are
high-entropy random values). MFA secrets: Fernet encryption with `DATA_ENCRYPTION_KEY`, managed
separately from the database. Credentials are never shown again after creation.
