# Incidents, remediation and reports (Phase 5)

## Incidents

An incident groups everything about one security event: what happened, the alerts and assets
involved, the evidence, who owns the response and what has been done.

### How incidents are opened

| Source | When |
| --- | --- |
| Automatic (correlation) | A **critical** alert is raised, or **3 or more high/critical alerts** hit the same asset within 24 hours |
| Joining | Any new alert on an asset that already has an open incident is linked to it, and raises the incident's severity if it is higher |
| Responder | Analysts, IT admins, admins and owners open one from the Incidents page or from an alert ("Open incident") |
| Staff report | Any member can report a suspected incident. Staff reports start as medium severity, and reporters see only their own reports |

The category (phishing, malware, account compromise, intrusion and so on) is suggested from the
detection rule and can be changed.

### Lifecycle

`open → investigating → contained → resolved → closed`. Closing requires an outcome (resolved,
false alarm, duplicate, risk accepted, other) and takes an optional lessons-learned summary. A
resolved or closed incident can be reopened. Assigning an owner notifies them, in-app and by
email, according to their notification preferences.

### Timeline and evidence

- Every change (status, owner, severity, linked assets or alerts, tasks, evidence, notes) is
  written to `incident_events`. The application database role cannot update or delete those
  rows, so the timeline is a permanent record.
- Evidence (screenshots, PDFs, logs, `.eml`/`.msg`, packet captures, zip files; up to 10 MB) is
  hashed with SHA-256 and stored with Fernet encryption under an organisation-prefixed key.
  Downloads check the hash and are sent as attachments that the browser will not render. Each
  download is audit-logged.

## Remediation

- **Fix tasks** come from findings ("Assign fix"). Without an explicit title, the task takes the
  finding's recommendation.
- **Containment and recovery tasks** belong to incidents.
- If no due date is given, it is set by priority: critical 1 day, high 7, medium 30, low 90.
- Status runs `open → in_progress → done → verified` (or `cancelled`). When monitoring confirms
  the finding is gone, the task is **verified by monitoring**. Marking a finding fixed verifies
  it manually. If a task is marked done after the finding has already been resolved, it is
  verified straight away. Accepting the risk, or removing the asset, cancels open tasks.
- Assignees without manage rights can only move their own tasks to in progress or done, and
  add a note.
- `GET /remediation/summary` reports open, in-progress, awaiting-verification and overdue tasks.
  It also gives the 30-day on-time rate, the median days to fix, and the number of urgent
  findings that nobody has been assigned to fix.

## Posture score (model v2)

| Component | Weight | Measures |
| --- | --- | --- |
| Findings | 35% | Open findings weighted by severity (critical 25, high 12, medium 5, low 1) |
| Coverage | 25% | Monitorable assets with data from the last 26 hours |
| Device health | 15% | Endpoint agents reporting and healthy |
| Remediation | 15% | Overdue tasks, and urgent findings that have gone unassigned too long |
| Incidents | 10% | Open incidents weighted by severity (critical 40, high 20, medium 10, low 5) |

A component without data (for example, no endpoints yet) is left out, and its weight is shared
across the rest. The score comes with a **confidence** value that reflects how much of the
estate is actually reporting. The overview shows both, with a breakdown by component.

## Reports

| Report | PDF | CSV |
| --- | --- | --- |
| Executive security summary | ✅ | |
| Asset inventory | ✅ | ✅ |
| Endpoint health | ✅ | ✅ |
| Findings | ✅ | ✅ |
| Incident history | ✅ | ✅ |
| Remediation progress | ✅ | ✅ |
| Monitoring coverage | ✅ | |

- Reports cover up to one year and default to the last 30 days. They are stored encrypted, and
  every download is audit-logged.
- CSV cells that start with `=`, `+`, `-` or `@` are neutralised, so spreadsheets don't run them as formulas.
- The monitor worker checks every hour. On the first run of each month it creates the previous
  month's executive summary for every active organisation and emails the owners and admins.
  This happens once per organisation per month.

## Permissions

| Permission | Owner | Admin | Analyst | IT admin | Auditor | Executive | Employee |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `incidents:report` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `incidents:read` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | |
| `incidents:manage` | ✅ | ✅ | ✅ | ✅ | | | |
| `remediation:read` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | own tasks |
| `remediation:manage` | ✅ | ✅ | ✅ | ✅ | | | |
| `reports:read` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | |
