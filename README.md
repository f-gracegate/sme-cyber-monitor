# SME Cybersecurity Monitoring

**Project 01 of 26**: business cybersecurity visibility, monitoring and risk management for
Ghanaian SMEs. Powered by GraceGate Technologies.

A multi-tenant SaaS platform that helps a small or medium business see what it needs to protect,
prove it is authorised to monitor it, detect problems and coordinate the response, without
running its own security operations centre.

> **Status: Phase 4 (network monitoring) complete.** The platform covers:
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
> Incidents, reports and the mobile app come next (see
> [docs/roadmap.md](docs/roadmap.md)).

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
```

The backend suite (121 tests) and the collector's own tests
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
agents/endpoint/    Reference endpoint agent (single Python file, standard library only)
agents/wazuh/       Wazuh manager integration script
agents/network-collector/  On-premises network collector (single Python file + Dockerfile)
backend/            FastAPI service, SQLAlchemy models, Alembic migrations, tests
infrastructure/     Database bootstrap (least-privilege roles)
docs/               PRD, architecture, database, API, threat model, deployment, roadmap
```

## Technology

Next.js 16 (App Router, TypeScript, Tailwind CSS 4) · Python 3.13 · FastAPI · SQLAlchemy 2 ·
Alembic · PostgreSQL 17 with Row-Level Security · Redis 7 · Docker. Android and iOS apps
(Flutter) arrive in Phase 6.

## Branding

The product name and the "Powered by" credit are configuration, not code. See
[apps/web/lib/brand.ts](apps/web/lib/brand.ts) (`NEXT_PUBLIC_*` variables) and
`BRAND_PRODUCT_NAME` on the backend.
