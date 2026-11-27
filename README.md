# SME Cybersecurity Monitoring

**Project 01 of 26**: business cybersecurity visibility, monitoring and risk management for
Ghanaian SMEs. Powered by GraceGate Technologies.

A multi-tenant SaaS platform that helps a small or medium business see what it needs to protect,
prove it is authorised to monitor it, detect problems and coordinate the response, without
running its own security operations centre.

> **Status: Phase 7 (pilot and production hardening) engineering complete.** The platform covers:
> - **Foundation (Milestone 1):** accounts, MFA, organisations, tenant isolation, roles and team
>   management, an asset inventory with ownership checks, audit history and plans.
> - **Websites and domains (Phase 2):** uptime, TLS, security headers, DNS and email-security
>   checks.
> - **Endpoints and servers (Phase 3):** computers and servers report through the reference
>   agent or a Wazuh connector. This covers enrolment, health findings, sign-in and malware
>   detections, offline alerts and a security event log
>   ([docs/endpoints.md](docs/endpoints.md)).
>
> - **Network (Phase 4):** on-site collectors forward firewall and router logs, Suricata and
>   Zeek output, and device reachability ([docs/network.md](docs/network.md)).
>
> - **Incidents and risk (Phase 5):** alerts are correlated into incidents. Each incident has a
>   permanent timeline, encrypted evidence, owners and response tasks. Findings get remediation
>   tasks that monitoring verifies, the posture score shows what drives it, and PDF/CSV reports
>   (including a monthly executive summary) can be produced
>   ([docs/incidents.md](docs/incidents.md)).
>
> - **Mobile and commercial (Phase 6):** Android and iOS companion apps for alert triage,
>   incidents and tasks, with push notifications and an optional biometric lock
>   ([docs/mobile.md](docs/mobile.md)). Plans are paid with Mobile Money or card through
>   Paystack, with trials, renewal reminders and receipts, and new businesses get a
>   getting-started checklist ([docs/billing.md](docs/billing.md)).
>
> - **Pilot and hardening (Phase 7):** a pre-launch security review with every finding fixed,
>   dependency, secret and container scanning in CI, hash-pinned dependencies, encrypted backups
>   with an automated restore drill, load tests, a production deployment (Caddy, HTTPS,
>   hardened containers, JSON logs, metrics), data-protection tools (retention, export,
>   organisation and account deletion), and pilot tools (alert outcomes, muting, feedback, pilot
>   measurements). See [security](docs/security.md), [operations](docs/operations.md),
>   [compliance](docs/compliance.md), [pilot](docs/pilot.md) and
>   [performance](docs/performance.md).
>
> Next: run the pilot with 5–10 businesses, and complete the owner tasks in
> [docs/compliance.md](docs/compliance.md) before commercial launch.

## Quick start

Requirements: Docker Desktop.

```bash
docker compose up --build
```

- Web app: <http://localhost:3810>
- API docs (development only): <http://localhost:8100/api/docs>

Sign in with the default platform administrator:

| Username | Password   |
| -------- | ---------- |
| `Admin`  | `password` |

You'll be asked to choose a new password on first sign-in. The seed also creates a **Demo
Business Ltd** organisation with six sample assets. In development its website and domain point at
`example.com` (reserved by IANA for documentation) and are pre-authorised, so live monitoring
results appear within a minute.

Invitation and password-reset emails are not sent in development. Open **Dev mailbox** in the
sidebar (platform admins) to follow their links.

To start again from a clean database:

```bash
docker compose down -v && docker compose up --build
```

## Tests and checks

To try endpoint monitoring, create a token under **Endpoints → Add devices** and start a
disposable Linux device: `SMECM_TOKEN=enr_... docker compose --profile demo up -d demo-agent`.
For network monitoring, create a collector under **Network → Add collector** and run
`SMECM_COLLECTOR_TOKEN=col_... docker compose --profile demo up -d demo-collector`.

The `monitor` service is the worker that runs scheduled checks. Run more than one with
`docker compose up --scale monitor=2`; they share work safely.

```bash
docker compose run --rm backend pytest
docker compose run --rm backend ruff check .
cd apps/web && npm ci && npm run lint && npx next build
cd apps/mobile && flutter analyze && flutter test
```

Restore drill: `scripts/restore-drill.sh`. Load test:
`docker compose exec backend python -m app.ops.loadtest`. Production deployment:
[docs/operations.md](docs/operations.md).

Payments use a simulated checkout in development (`PAYMENT_PROVIDER=sandbox`): choose a plan
under **Settings → Subscription** and approve or decline the test payment. Pushes go to a
development outbox (`GET /api/v1/dev/push`) until Firebase is configured.

The backend suite (198 tests) and the collector's own tests
(`python -m unittest discover -s agents/network-collector -t agents/network-collector`)
include the release-blocking security scenarios: cross-tenant
access, database-level Row-Level Security, forged organisation headers, privilege escalation,
revoked members, refresh-token reuse, MFA replay, SSRF protection (including via redirects), and
the finding/alert lifecycle: deduplication, auto-resolution, and the rule that missing data never
clears a finding, plus agent enrolment, forged organisation IDs, expired tokens, malformed
telemetry, brute-force detection, the Wazuh connector, collector probes limited to authorised
devices, and network detections.

## Repository layout

```
apps/web/           Next.js 16 + TypeScript web application
apps/mobile/        Flutter companion app for Android and iOS
agents/endpoint/    Reference endpoint agent (single Python file, standard library only)
agents/wazuh/       Wazuh manager integration script
agents/network-collector/  On-premises network collector (single Python file + Dockerfile)
backend/            FastAPI service, SQLAlchemy models, Alembic migrations, tests
infrastructure/     Database bootstrap (least-privilege roles)
deploy/             Production Compose stack, Caddy, backup/restore tooling, restore drill
scripts/            Restore drill
docs/               PRD, architecture, database, API, threat model, deployment, roadmap
```

## Technology

Next.js 16 (App Router, TypeScript, Tailwind CSS 4) · Python 3.13 · FastAPI · SQLAlchemy 2 ·
Alembic · PostgreSQL 17 with Row-Level Security · Redis 7 · Docker · Flutter 3.47 (Android and
iOS) · Firebase Cloud Messaging · Paystack (Mobile Money and card).

## Branding

The product name and the "Powered by" credit are configuration, not code. See
[apps/web/lib/brand.ts](apps/web/lib/brand.ts) (`NEXT_PUBLIC_*` variables) and
`BRAND_PRODUCT_NAME` on the backend.
