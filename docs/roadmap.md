# Roadmap

Estimates are engineering targets, not guaranteed dates. Phases overlap where practical.

| Phase | Scope | Status |
| --- | --- | --- |
| 1. Foundation (wk 1–4) | Repo, database, auth + MFA, organisations, tenant isolation, roles, design system, audit log, asset inventory | ✅ Milestone 1 delivered |
| 2. External asset monitoring (wk 5–8) | Scheduler, uptime, DNS, TLS, security headers, email security, findings, alerts, notifications, posture score and trend | ✅ Delivered |
| 3. Endpoint & server monitoring (wk 9–14) | Wazuh evaluation, agent enrolment, health, event ingestion, detection rules, endpoint screens | Next |
| 4. Network monitoring (wk 15–19) | Collector, firewall/device logs, Suricata, Zeek evaluation, network dashboards | |
| 5. Incident & risk management (wk 20–22) | Correlation, risk scoring, incidents, remediation, reports | |
| 6. Mobile & commercial (wk 23–26) | Flutter Android/iOS, push notifications, billing (MoMo/card), onboarding | |
| 7. Pilot & hardening (wk 27–36) | Security and performance testing, regulatory readiness, 5–10 pilot customers | |

## Milestone 1 deliverable

A running application where a business can register, sign in (with MFA), create its
organisation, invite users with roles, and register and authorise its digital assets.

## Phase 2 deliverable

Authorised websites and domains are checked on a schedule (uptime every 5 minutes, DNS hourly,
headers every 6 hours, TLS and email security every 12 hours; all adjustable). 28 plain-English
rules turn results into findings with severity, impact and fix. Repeats are grouped into one
alert; alerts close themselves when the problem clears. Everyone whose role can see alerts gets
in-app notifications (low and above) and email (high and above) by default, each adjustable per
person. The overview shows a posture score, daily trend, findings and alerts by severity,
recent alerts and the most exposed assets.
