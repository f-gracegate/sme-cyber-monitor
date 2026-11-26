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

## Endpoints (Milestone 1)

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
| Platform | GET | `/platform/organisations` (platform admins) |
| Health | GET | `/api/health` |

Agent and collector ingestion endpoints (Phase 3–4) will authenticate with device credentials
and strict schema validation, not user sessions, and will derive the organisation from the
enrolled device, never from the payload.
