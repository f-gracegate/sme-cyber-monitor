# Roadmap

Estimates are engineering targets, not guaranteed dates. Phases overlap where practical.

| Phase | Scope | Status |
| --- | --- | --- |
| 1. Foundation (wk 1–4) | Repo, database, auth + MFA, organisations, tenant isolation, roles, design system, audit log, asset inventory | ✅ Milestone 1 delivered |
| 2. External asset monitoring (wk 5–8) | Scheduler, uptime, DNS, TLS, security headers, email security, findings, alerts, notifications, posture score and trend | ✅ Delivered |
| 3. Endpoint & server monitoring (wk 9–14) | Wazuh evaluation, agent enrolment, health, event ingestion, detection rules, endpoint screens | ✅ Delivered |
| 4. Network monitoring (wk 15–19) | Collector, firewall/device logs, Suricata, Zeek evaluation, network dashboards | ✅ Delivered |
| 5. Incident & risk management (wk 20–22) | Correlation, risk scoring, incidents, remediation, reports | ✅ Delivered |
| 6. Mobile & commercial (wk 23–26) | Flutter Android/iOS, push notifications, billing (MoMo/card), onboarding | ✅ Delivered |
| 7. Pilot & hardening (wk 27–36) | Security and performance testing, regulatory readiness, 5–10 pilot customers | ✅ Engineering delivered; pilot to run |

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

## Phase 3 deliverable

Devices enrol with short-lived tokens and report through the reference agent or a Wazuh manager.
They become authorised assets automatically, report health (antivirus, firewall, encryption,
updates, disk, OS support) and send security events. Detections cover brute force, sign-in after
brute force, malware, tampering, new admin accounts, log clearing, suspicious processes and
removable media. Silent agents raise a "stopped reporting" finding. See
[endpoints.md](endpoints.md).

## Phase 4 deliverable

An on-premises collector (single Python file or Docker image) receives syslog from common
firewalls and routers, tails Suricata and Zeek output, checks that authorised network devices
are reachable, and forwards filtered, aggregated events over outbound HTTPS. The Network page
shows collectors, device availability, blocked connections, configuration changes and, only
when a sensor exists, intrusion and traffic summaries. See [network.md](network.md).

## Phase 5 deliverable

Critical alerts, and three or more high-severity alerts on one asset within 24 hours, open
incidents automatically. Later alerts on the same asset join the open incident. Responders work
each incident through open, investigating, contained, resolved and closed. Every incident has
an append-only timeline, encrypted evidence with SHA-256 integrity checks, affected assets,
related alerts and containment/recovery tasks. Staff can report suspected incidents and see
only their own reports.

Findings get remediation tasks with owners and due dates set by severity. A task is verified
automatically when monitoring confirms the problem is gone. The posture score (model v2)
combines findings, monitoring coverage, device health, remediation timeliness and open
incidents, and it reports a confidence level. Seven report types are available as PDF, five
of them also as CSV. An executive summary is generated and emailed on the 1st of each month.
See [incidents.md](incidents.md).

## Phase 6 deliverable

- **Mobile app** (Flutter, one codebase for Android and iOS) for alert triage, incidents,
  assigned tasks and the notification inbox. Sign-in uses the same accounts with MFA and
  temporary-password changes. Tokens live in the Keychain / Android Keystore, and an optional
  Face ID / fingerprint lock is available. Staff can report incidents from their phone. CI
  builds Android and iOS on every push.
- **Push notifications** through Firebase Cloud Messaging (APNs for iOS). They follow the same
  audience rules as in-app notifications, with a per-person "push me about" level (default high
  and critical). Lock-screen text names only the severity and alert title. Pushes stop when the
  phone signs out.
- **Billing**: monthly or yearly (two months free) prepaid plans, paid with Mobile Money (MTN,
  Telecel, AirtelTigo) or card through Paystack's hosted checkout. Payments are verified on the
  server and signed webhooks are checked. Plan changes credit unused time, and downgrades are
  checked against usage. Each payment gets a PDF receipt. Trials and paid plans move through
  past-due (7-day grace) to expired, with reminders 7, 3 and 1 day before the end. Expired
  organisations keep their data and monitoring but can't add assets, people or devices.
- **Onboarding**: a getting-started checklist that follows the business onboarding journey
  (profile, first asset, ownership proof, first results, team, MFA, then the optional agent,
  phone and plan). It appears on the overview and in the navigation until it is done or hidden.

Store submission (Apple and Google developer accounts, signing keys, Firebase project, privacy
labels) and the production Paystack account are owner tasks before the pilot.

## Phase 7 deliverable

- **Security testing:** an independent pre-launch code review, with all twelve findings fixed
  and tested ([security.md](security.md)). Fixes include fail-closed configuration, safe device
  re-enrolment, MFA brute-force protection, email verification, push-token ownership,
  same-site redirects and staff-limited overviews. CI scans dependencies (pip-audit,
  npm audit), secrets (gitleaks) and containers and configuration (Trivy). Python dependencies
  are hash-pinned, and Dependabot is on.
- **Performance testing:** a load-test harness shows dashboard p95 132 ms at about 286
  requests/s, about 2,600 events/s ingested with no server errors, and alerts visible in under
  a second ([performance.md](performance.md)).
- **Recovery:** nightly encrypted backups with checksummed manifests, a guarded restore, and
  an automated restore drill into a clean server, run in CI (security scenario 10).
- **Operations:** a production Compose stack with Caddy (automatic HTTPS, security headers),
  read-only non-root containers, password-protected Redis, JSON logs with request IDs,
  Prometheus metrics, a worker heartbeat and a runbook ([operations.md](operations.md)).
- **Regulatory readiness (Act 843 / Act 1038):**
  - per-organisation telemetry retention within plan limits
  - full data export
  - owner-requested organisation erasure after a 30-day cooling-off period
  - self-service account deletion
  - expanded privacy notice and terms
  - records of processing and the owner's regulatory task list
    ([compliance.md](compliance.md))
- **Pilot tools:**
  - alert outcomes, including "Not a real problem", to measure false positives
  - muting rules for known conditions (critical alerts can't be muted)
  - an in-product feedback button
  - a platform pilot-measurements dashboard covering every measure in the plan
    ([pilot.md](pilot.md))

Remaining before commercial launch (owner): run the pilot, the external penetration test, a
lawyer's review, DPC registration, written CSA classification, the hosting decision, tax and
VAT, insurance, signed agent packages, and store submissions for the mobile apps.

