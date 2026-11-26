# Roadmap

Estimates are engineering targets, not guaranteed dates. Phases overlap where practical.

| Phase | Scope | Status |
| --- | --- | --- |
| 1. Foundation (wk 1–4) | Repo, database, auth + MFA, organisations, tenant isolation, roles, design system, audit log, asset inventory | ✅ Milestone 1 delivered |
| 2. External asset monitoring (wk 5–8) | Scheduler, uptime, DNS, TLS, security headers, findings, alerts, notifications, dashboard data | Next |
| 3. Endpoint & server monitoring (wk 9–14) | Wazuh evaluation, agent enrolment, health, event ingestion, detection rules, endpoint screens | |
| 4. Network monitoring (wk 15–19) | Collector, firewall/device logs, Suricata, Zeek evaluation, network dashboards | |
| 5. Incident & risk management (wk 20–22) | Correlation, risk scoring, incidents, remediation, reports | |
| 6. Mobile & commercial (wk 23–26) | Flutter Android/iOS, push notifications, billing (MoMo/card), onboarding | |
| 7. Pilot & hardening (wk 27–36) | Security and performance testing, regulatory readiness, 5–10 pilot customers | |

## Milestone 1 deliverable

A running application where a business can register, sign in (with MFA), create its
organisation, invite users with roles, and register and authorise its digital assets.
