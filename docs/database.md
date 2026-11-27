# Database

PostgreSQL is the system of record. Migrations live in `backend/migrations/versions` and run as
the owner role; the application uses the least-privileged `smecm_app` role
(`infrastructure/database/init/01-roles.sh`).

## Tables

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
| `monitoring_checks` | Scheduled check per asset and type, with state between runs | ✅ | ✅ |
| `check_runs` | Result of each run (kept 30 days) | ✅ | ✅ |
| `findings` | One row per asset and rule; open, resolved or accepted risk | ✅ | ✅ |
| `alerts` | At most one unresolved alert per finding (partial unique index) | ✅ | ✅ |
| `notifications` | Per-user in-app notifications | ✅ | ✅ (user + org) |
| `notification_preferences` | Per-user email and in-app severity thresholds | ✅ | ✅ |
| `risk_score_history` | Daily posture score per organisation | ✅ | ✅ |
| `agent_enrolment_tokens` | Hashed, expiring, limited-use device enrolment tokens | ✅ | ✅ |
| `agents` | One monitoring agent per device (reference agent or Wazuh), hashed credential, latest inventory | ✅ | ✅ |
| `security_events` | Normalised endpoint events, idempotent per agent, kept 30 days | ✅ | ✅ |
| `integration_keys` | Hashed organisation keys for connected tools (Wazuh) | ✅ | ✅ |

| `incidents` | Per-organisation numbered incidents (INC-0001), lifecycle timestamps, owner, closure reason | ✅ | ✅ |
| `incident_assets`, `incident_alerts` | Affected assets and correlated alerts | ✅ | ✅ |
| `incident_events` | Append-only incident timeline (`UPDATE`/`DELETE` revoked) | ✅ | ✅ |
| `incident_evidence` | Evidence metadata and SHA-256; the file is Fernet-encrypted in object storage | ✅ | ✅ |
| `remediation_tasks` | Fix, containment and recovery tasks, owner, due date, verification method | ✅ | ✅ |
| `reports` | Generated reports (type, period, format); the file is encrypted in object storage | ✅ | ✅ |

| `payments` | Checkout attempts and paid periods: plan, amount in pesewas, channel, safe payment-method summary, receipt number, credited days. The app role cannot `DELETE` | ✅ | ✅ |
| `push_devices` | Phones registered for push: Fernet-encrypted FCM token, SHA-256 token hash, the session that registered it. Private to the user (RLS on `user_id`) | — | ✅ |

| `suppression_rules` | Muted alert kinds per organisation (rule, asset or all, reason, expiry, hit count) | ✅ | ✅ |
| `feedback` | In-product feedback (kind, message, page, rating, triage status). Private to its author (RLS on `user_id`); the platform team reads it | — | ✅ |
| `data_exports` | Organisation data exports (encrypted zip in object storage, SHA-256, 7-day expiry) | ✅ | ✅ |

Migration 0008 adds `users.email_verified_at` (existing accounts backfilled as verified),
`alerts.outcome`, `organisations.telemetry_retention_days` and the deletion fields
(`deletion_requested_at`, `deletion_requested_by`, `deletion_scheduled_for`, `deleted_at`).
Erasure deletes every organisation-scoped row except `audit_logs`, `payments`, `subscriptions`
and `feedback` (de-linked), and keeps a pseudonymised organisation row.

Migration 0007 also adds `subscriptions.last_reminder`, `organisations.onboarding_dismissed_at`,
`auth_sessions.client` (`web` or `mobile`), `notifications.pushed_at` and
`notification_preferences.push_min_severity`.

`risk_score_snapshots` also stores the score components and a confidence value (migration 0006).

`audit_logs` grants the application `INSERT` and `SELECT` only. `UPDATE`, `DELETE` and `TRUNCATE`
are revoked, and a test asserts it.

## Planned (later phases)

`monitoring_profiles`, `usage_records`, `invoices` (VAT invoices once registered), `detection_rules`,
`event_envelopes`, `event_sources`, `api_keys`, `alert_rules`,
`data_retention_policies`, `asset_discovery_jobs`.

High-volume raw telemetry will go to an indexed event store (OpenSearch evaluation), not
ordinary relational tables. PostgreSQL keeps the authoritative business records.

## Secrets at rest

Passwords and recovery codes: Argon2id. Refresh, reset and invitation tokens: SHA-256 (they are
high-entropy random values). MFA secrets: Fernet encryption with `DATA_ENCRYPTION_KEY`, managed
separately from the database. Credentials are never shown again after creation.
