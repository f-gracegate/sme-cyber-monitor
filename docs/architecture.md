# Architecture

## Today (Milestone 1)

```
Browser ──HTTPS──▶ Next.js web app ──/api/* rewrite──▶ FastAPI ──▶ PostgreSQL (RLS)
                    (same origin)                        │
                                                         └──────▶ Redis (rate limits, dev mail)
```

- **Same-origin API.** The browser only talks to the Next.js origin; `/api/*` is proxied to
  FastAPI. Session cookies stay first-party, `HttpOnly`, `SameSite=Lax`, and no CORS is needed.
- **Client-rendered workspace.** Signed-in pages render in the browser after the session is
  confirmed (`/api/v1/auth/me`). Auth pages and module previews are prerendered.
- **Modular monolith backend.** One FastAPI service with clear module boundaries (auth,
  organisations, assets, workspace). Workers for monitoring, detection and notifications are
  added as separate processes in later phases, so a burst of telemetry can't take the dashboard
  down.

## Target system

```
Customer environment                  Platform
────────────────────                  ────────────────────────────────────────────────
Windows/macOS/Linux agents ─┐         Next.js web ──▶ FastAPI API ──▶ PostgreSQL
Network sensor/collector  ──┼─TLS────▶ Telemetry ingestion ──▶ Redis queue
Servers & cloud workloads ─┘         Monitoring & detection workers ──▶ Risk engine
                                      Website/DNS/TLS workers ──▶ authorised public assets
                                      Notification service · Reports · Object storage
```

Collection methods: cloud workers (public websites and domains), endpoint agents (Wazuh
integration evaluated first), and an optional on-premises network collector that sends approved
telemetry over authenticated outbound TLS. Customers never expose internal management
interfaces to the internet.

## Tenant isolation (defence in depth)

1. Every tenant-owned row carries `organisation_id`.
2. Every organisation-scoped request resolves the caller's **active membership** before anything
   else (`app/api/deps.py`). Unknown and forbidden organisations both return 404.
3. Every query is filtered by organisation in code.
4. **PostgreSQL Row-Level Security** enforces the same boundary in the database. The app
   connects as `smecm_app`, which owns no tables. Each transaction sets
   `app.current_org`/`app.current_user` with `set_config(..., is_local => true)`.
5. Background work will derive the tenant from trusted records, never from event payloads.
6. Tests deliberately attempt cross-tenant access through the API and directly in SQL.

A narrow `system_context()` bypass exists for seeding, platform counts and invitation-token
lookups; it is never reachable from request input.

## Authentication

- Argon2id password hashing, a 12-character minimum and common-password rejection.
- Short-lived (15 min) signed access token in an `HttpOnly` cookie, backed by a server-side
  session row so sign-out and revocation take effect immediately.
- Rotating refresh token (stored hashed). Reusing a rotated token revokes the session.
- Double-submit CSRF token for cookie-authenticated writes; bearer tokens for future mobile/API.
- TOTP MFA with replay protection, encrypted secret at rest (Fernet) and hashed one-time
  recovery codes. Organisations can require MFA for all members.
- Account lockout after repeated failures, plus Redis rate limits per IP and per account.

## Asset authorisation

Websites and domains must prove control (DNS TXT record or a `/.well-known` file) before they
can ever be monitored. The HTTP check resolves once, refuses private, loopback, link-local and
metadata addresses, connects to the validated IP with the original Host/SNI, never follows
redirects and reads at most 1 KB. Internal assets are confirmed by an administrator (audited)
until agent enrolment provides technical proof.

## Scoring principles

Finding severity and organisation posture are separate. The posture score is **not shown** until
monitoring data exists, and missing telemetry is shown as a coverage gap instead of quietly
improving the score.
