# Regulatory readiness (Phase 7)

This is an engineering view of what the product does to support compliance. It is **not legal
advice**. The owner tasks at the end need a Ghanaian lawyer and written answers from the
regulators.

## Data Protection Act, 2012 (Act 843)

| Requirement | How the product supports it |
| --- | --- |
| Roles | Customers are controllers for the security data they send; GraceGate is their processor (and controller for account and billing data). Stated in the privacy notice (`/legal/privacy`) |
| Minimisation | Agents collect security metadata only: no file contents, keystrokes or browsing history. Push messages carry only severity and title. Card and wallet details stay with Paystack |
| Security | Per-tenant isolation in the database (RLS), encryption in transit (TLS) and at rest (Fernet for files and secrets, encrypted backups), Argon2id passwords, MFA, audit trail |
| Retention | Per-organisation telemetry retention (7–365 days by plan), notifications 180 days, exports 7 days, erasure 30 days after a deletion request |
| Data-subject rights | **Access/portability:** organisation export (zip of JSON). **Erasure:** organisation deletion and self-service account deletion. **Correction:** profile and asset editing. Employees go through their employer (the controller) |
| Accountability | Append-only audit log of security-relevant actions, including exports, downloads, deletions, muting and retention changes |
| Breach notification | Runbook in [operations.md](operations.md). The audit trail and request IDs support the investigation |

### Records of processing (summary)

| Activity | Data subjects | Data | Purpose | Retention |
| --- | --- | --- | --- | --- |
| Accounts | Customer staff | Name, email, role, sign-in history | Provide and secure the service | Life of the account |
| Asset monitoring | — (business systems) | Domains, websites, TLS/DNS/header results | Detect weaknesses | Plan retention for raw results |
| Endpoint monitoring | Customer employees | Hostname, logged-in user names, sign-in events, security events | Detect threats | Plan retention |
| Network monitoring | Customer employees and visitors | IP addresses, firewall and IDS events | Detect threats | Plan retention |
| Incidents | Customer staff, possibly third parties | Notes, evidence files | Respond to incidents | Life of the customer |
| Billing | Customer owners | Plan, amounts, card brand / last digits, MoMo network | Billing and tax | As tax law requires |
| Mobile push | Customer staff | Device push token | Deliver alerts | Until sign-out or removal |

## Cybersecurity Act, 2020 (Act 1038)

The product plan's position stands. Selling the software is different from delivering managed
monitoring or response. The CSA licenses cybersecurity service providers and accredits
establishments such as SOCs. Until there is written guidance:

- Position the pilot as **software the customer operates**. Don't monitor or respond on
  customers' behalf for a fee.
- Keep the terms wording that managed services, where offered, are subject to CSA licensing.

## Owner tasks before commercial launch

1. **Lawyer:** review the privacy notice and terms, draft the data-processing agreement, and
   advise on breach-notification timelines.
2. **Data Protection Commission:** register GraceGate Technologies as a data controller/processor
   and renew annually.
3. **Cyber Security Authority:** ask in writing how the product is classified and whether a
   licence is needed for the planned services. Keep the reply on file.
4. **Hosting:** choose the provider and region after reviewing data residency, contracts and
   backup locations, then record the decision.
5. **Tax:** decide on VAT/levies and invoicing. Today's receipts are not VAT invoices.
6. **Insurance:** professional indemnity / cyber liability cover before taking paying
   customers.
