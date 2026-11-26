# API

Interactive OpenAPI docs: `http://localhost:8100/api/docs` (development only).

## Conventions

- Base path `/api/v1`. Versioned.
- Organisation-scoped resources (`/assets`, `/overview`, `/audit-logs`, `/billing/*`) need
  `X-Organisation-Id`. Routes under `/organisations/{id}/…` take the ID from the path.
- Browser auth: `HttpOnly` cookies plus an `X-CSRF-Token` header echoing the `smecm_csrf` cookie
  on every write. Other clients: `Authorization: Bearer <access token>`.
- Errors: `{"error": {"code", "message", "details?"}, "request_id"}`. Every response carries
  `X-Request-ID`.
- Lists: `{"items", "total", "page", "page_size"}` with `page` / `page_size` (max 100).

## Endpoints

| Area | Method | Path |
| --- | --- | --- |
| Auth | POST | `/auth/register`, `/auth/login`, `/auth/mfa/verify`, `/auth/refresh`, `/auth/logout` |
| Auth | GET | `/auth/me` |
| Password | POST | `/auth/password/change`, `/auth/password/forgot`, `/auth/password/reset` |
| MFA | POST | `/auth/mfa/setup`, `/auth/mfa/enable`, `/auth/mfa/disable` |
| Invitations | GET | `/auth/invitations/{token}` (preview) |
| Invitations | POST | `/auth/invitations/accept` |
| Roles | GET | `/roles` |
| Organisations | GET, POST | `/organisations` |
| Organisations | GET, PATCH | `/organisations/{id}` |
| Members | GET | `/organisations/{id}/members` |
| Members | PATCH, DELETE | `/organisations/{id}/members/{membership_id}` |
| Invitations | GET, POST | `/organisations/{id}/invitations` |
| Invitations | DELETE | `/organisations/{id}/invitations/{invitation_id}` |
| Departments | GET, POST | `/organisations/{id}/departments` |
| Departments | DELETE | `/organisations/{id}/departments/{department_id}` |
| Assets | GET, POST | `/assets` |
| Assets | GET, PATCH | `/assets/{id}` |
| Assets | POST | `/assets/{id}/archive`, `/assets/{id}/restore` |
| Verification | POST | `/assets/{id}/verification` (start), `/assets/{id}/verify` (check) |
| Activity | GET | `/assets/{id}/activity` |
| Overview | GET | `/overview` |
| Audit | GET | `/audit-logs` |
| Billing | GET | `/billing/subscription` |
| Monitoring | GET | `/monitoring/summary`, `/monitoring/checks`, `/monitoring/runs` |
| Monitoring | POST | `/monitoring/checks`, `/monitoring/checks/{id}/run` |
| Monitoring | PATCH | `/monitoring/checks/{id}` (enable/disable, interval) |
| Findings | GET | `/findings`, `/findings/{id}` |
| Findings | PATCH | `/findings/{id}` (open, resolved, accepted_risk + note) |
| Alerts | GET | `/alerts`, `/alerts/{id}` |
| Alerts | PATCH | `/alerts/{id}` (new, acknowledged, investigating, resolved) |
| Notifications | GET | `/notifications`, `/notifications/preferences` |
| Notifications | POST, PUT | `/notifications/read`, `/notifications/preferences` |
| Endpoints | GET | `/endpoints`, `/endpoints/summary`, `/endpoints/events` |
| Endpoints | POST | `/endpoints/{id}/revoke` |
| Enrolment | GET, POST | `/endpoints/enrolment-tokens` |
| Enrolment | DELETE | `/endpoints/enrolment-tokens/{id}` |
| Integrations | GET, POST | `/integrations/keys` |
| Integrations | DELETE | `/integrations/keys/{id}` |
| Agent (device credential) | POST | `/agent/enrol` (token), `/agent/heartbeat`, `/agent/events` |
| Agent (public) | GET | `/agent/release`, `/agent/download`, `/agent/wazuh-integration` |
| Wazuh (integration key) | POST | `/integrations/wazuh/alerts` |
| Network | GET | `/network/summary`, `/network/collectors`, `/network/devices` |
| Collector (token / credential) | POST | `/collector/enrol`, `/collector/heartbeat`, `/collector/events` |
| Collector (public) | GET | `/collector/release`, `/collector/download` |
| Incidents | GET | `/incidents` (status, severity, `q` title or INC number, `mine`), `/incidents/{id}` |
| Incidents | POST | `/incidents`, `/incidents/{id}/notes`, `/incidents/{id}/assets`, `/incidents/{id}/alerts` |
| Incidents | PATCH | `/incidents/{id}` (status, owner, severity, category; closing needs `closure_reason`) |
| Evidence | POST, GET | `/incidents/{id}/evidence` (multipart, 10 MB), `/incidents/{id}/evidence/{evidence_id}` |
| Remediation | GET | `/remediation-tasks` (status, `mine`, `overdue`, `finding_id`, `incident_id`), `/remediation/summary` |
| Remediation | POST, PATCH | `/remediation-tasks`, `/remediation-tasks/{id}` |
| Reports | GET | `/reports/types`, `/reports`, `/reports/{id}/download` |
| Reports | POST | `/reports` (type, format, period up to one year) |
| Platform | GET | `/platform/organisations` (platform admins) |
| Health | GET | `/api/health` |

Agent endpoints authenticate with `Authorization: Agent <agent_id>:<secret>`. The Wazuh
endpoint uses `Authorization: Bearer smecm_int_…`. Neither uses user sessions. The organisation
always comes from the enrolled agent or the integration key, never from the payload, and
unexpected fields are rejected. Collectors use the same `Agent` scheme with their own
credentials; the two kinds can't use each other's endpoints. Enrolment tokens take
`"kind": "agent" | "collector"`. `/endpoints/events` accepts `category=endpoint|network`.
