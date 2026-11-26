# Product requirements: SME Cybersecurity Monitoring

Version 1.0 · 26 November 2026 · Project 01 of 26

## Vision

A cybersecurity monitoring and management platform that lets an SME see what is happening across
its digital environment, find weaknesses, detect suspicious activity and coordinate remediation,
without an in-house Security Operations Centre.

**Positioning:** business cybersecurity visibility, monitoring and risk management in one platform.

Four operating capabilities: **Discover** authorised assets → **Monitor** websites, endpoints,
servers and networks → **Detect** suspicious activity and weaknesses → **Respond** with alerts,
remediation and reports.

The platform provides monitoring, detection and response *coordination*. Automated containment
(for example isolating a computer) comes only after the endpoint agent, safety controls and
operating processes are independently tested.

## Confirmed decisions

| Decision | Direction |
| --- | --- |
| Market | General Ghanaian SMEs across industries |
| Monitoring scope | Websites, computers, servers and networks |
| Platforms | Web first; Android and iOS companion apps, each released when it passes its own testing |
| Commercial model | Subscription SaaS, optional managed services (subject to CSA licensing) |
| Architecture | Multi-tenant, API-driven, modular |
| Brand | Product: "SME Cybersecurity Monitoring", powered by GraceGate Technologies (configurable) |

## Monitoring environments

| Environment | Examples | Collection |
| --- | --- | --- |
| External assets | Websites, domains, DNS, TLS, security headers | Cloud workers |
| Endpoints | Windows, macOS, Linux health and security events | Endpoint agent |
| Servers and cloud | Logs, services, patches, auth events, backups | Agent and integrations |
| Networks | Firewall logs, DNS, traffic metadata, IDS | On-premises collector |

## Functional requirements

| ID | Requirement | Priority | Status |
| --- | --- | --- | --- |
| FR-001 | User registration and secure authentication | Must | ✅ Milestone 1 |
| FR-002 | Organisation creation and workspace isolation | Must | ✅ Milestone 1 |
| FR-003 | Invite and manage organisation members | Must | ✅ Milestone 1 |
| FR-004 | Register and verify authorised assets | Must | ✅ Milestone 1 |
| FR-005 | Monitor websites and domain configurations | Must | ✅ Phase 2 |
| FR-006 | Schedule monitoring checks | Must | ✅ Phase 2 |
| FR-007 | Install, register and manage endpoint agents | Must | ✅ Phase 3 |
| FR-008 | Collect and normalise endpoint security events | Must | ✅ Phase 3 |
| FR-009 | Register servers and collect security telemetry | Must | ✅ Phase 3 (health + events) |
| FR-010 | Receive network telemetry through a collector | Must | ✅ Phase 4 |
| FR-011 | Generate findings from monitoring data | Must | ✅ Phase 2 |
| FR-012 | Correlate related events into alerts | Must | ✅ Dedup/grouping (Phase 2); cross-event correlation Phase 5 |
| FR-013 | Prioritise risks and display severity | Must | ✅ Phase 2 |
| FR-014 | Assign remediation tasks | Must | Phase 5 |
| FR-015 | Record incident investigations | Must | Phase 5 |
| FR-016 | Notify authorised users | Must | ✅ In-app + email (Phase 2); push Phase 6 |
| FR-017 | Generate management reports | Must | Phase 5 |
| FR-018 | Maintain searchable audit logs | Must | ✅ Milestone 1 |
| FR-019 | Provide role-based access control | Must | ✅ Milestone 1 |
| FR-020 | Provide subscriptions and usage limits | Must | ✅ Limits; payments Phase 6 |
| FR-021 | Mobile push notifications | Should | Phase 6 |
| FR-022 | Mobile incident management | Should | Phase 6 |
| FR-023 | Integrate third-party security tools | Should | ✅ Wazuh (Phase 3); Suricata, Zeek, firewall syslog (Phase 4) |
| FR-024 | Automated containment actions | Later | — |
| FR-025 | Threat intelligence enrichment | Later | — |

## Roles

| Role | Can |
| --- | --- |
| Platform Super Administrator | Operate the platform and view customer organisations (counts only) |
| Organisation Owner | Everything in the organisation, including billing and other owners |
| Organisation Administrator | Users, assets, monitoring and settings |
| Security Analyst | Investigate alerts, review findings, manage incidents |
| IT Administrator | Endpoints, servers, agents, network collectors and assets |
| Auditor / Compliance Viewer | Read reports, findings and audit records |
| Standard Employee | Report incidents, see assigned tasks |
| Executive Viewer | High-level posture, reports and trends |

Access is enforced by the API (and, for tenant boundaries, by PostgreSQL), never only by hiding
buttons. The exact permission matrix is in `backend/app/security/rbac.py`.

## Non-functional targets

Web availability 99.5% monthly (MVP) · API p95 < 500 ms for normal requests · dashboard usable
within 3 s · 95% of eligible events alerted within 2 min · no cross-organisation data access ·
security actions audited with actor and time · encryption in transit and at rest · keyboard
navigation, readable contrast, responsive layouts · tested backups and recovery.

## Release rule

No unresolved critical vulnerabilities, no known cross-tenant access flaw and no untested backup
recovery procedure at commercial launch.
