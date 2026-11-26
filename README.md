# SME Cybersecurity Monitoring

**Project 01 of 26**: business cybersecurity visibility, monitoring and risk management for
Ghanaian SMEs. Powered by GraceGate Technologies.

A multi-tenant SaaS platform that helps a small or medium business see what it needs to protect,
prove it is authorised to monitor it, detect problems and coordinate the response, without
running its own security operations centre.

> **Status: Milestone 1 (application foundation).** Accounts, MFA, organisations and tenant
> isolation, roles, team management, asset inventory with ownership verification, audit history,
> plans and the dashboard shell are working. Website, endpoint and network monitoring, findings,
> alerts, incidents, reports and the mobile app follow in later phases (see
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
Business Ltd** organisation with six sample assets.

Invitation and password-reset emails are not sent in development. Open **Dev mailbox** in the
sidebar (platform admins) to follow their links.

To start again from a clean database:

```bash
docker compose down -v && docker compose up --build
```

## Tests and checks

```bash
docker compose run --rm backend pytest
docker compose run --rm backend ruff check .
cd apps/web && npm ci && npm run lint && npx next build
```

The backend suite includes the release-blocking security scenarios: cross-tenant access,
database-level Row-Level Security, forged organisation headers, privilege escalation, revoked
members, refresh-token reuse, MFA replay and SSRF protection for ownership checks.

## Repository layout

```
apps/web/           Next.js 16 + TypeScript web application
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
