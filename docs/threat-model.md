# Threat model

The platform receives security information from many businesses, which makes it a high-value
target. Status reflects Milestone 1.

| Threat | Mitigation | Status |
| --- | --- | --- |
| Cross-tenant data access | Membership check on every request, query scoping, PostgreSQL RLS, 404 for foreign IDs, automated tests | ✅ |
| Account takeover | Argon2id, password policy, lockout, IP and account rate limits, TOTP MFA, org-wide MFA requirement | ✅ |
| Session theft | HttpOnly cookies, short-lived access tokens backed by revocable sessions, rotating refresh with reuse detection | ✅ |
| CSRF | SameSite=Lax cookies plus double-submit CSRF token on writes | ✅ |
| Privilege escalation | Server-side permission matrix; only owners grant owner; no self role changes; last owner protected | ✅ |
| Former employee access | Membership removal or suspension takes effect on the next request | ✅ |
| SSRF via ownership checks and monitoring | Public-IP-only resolution, pinned connection, every redirect hop re-validated, tiny reads, timeouts | ✅ (a dedicated egress proxy is recommended in production) |
| Monitoring someone else's site | Websites and domains need DNS or file proof of control | ✅ |
| Audit tampering | App role cannot UPDATE/DELETE audit rows | ✅ |
| Open redirect after login | `next` parameter restricted to same-site paths | ✅ |
| Misleading score from missing data | Findings only clear after a successful run; failed or disabled checks shown as coverage gaps | ✅ |
| Malicious agent / telemetry poisoning | Per-device hashed credentials, short-lived limited-use enrolment tokens, strict schemas (extra fields rejected), size and rate limits, idempotent events, tenant derived from enrolment | ✅ (signed agent packages before launch) |
| Alert flooding | One open alert per finding (enforced by a unique index), occurrence counters, auto-resolution; suppression rules Phase 5 | ✅ Partial |
| Credential theft (integrations) | Integration keys and agent credentials stored as hashes, shown once, revocable | ✅ |
| Supply chain | Locked dependencies, CI checks; image scanning and signed agent packages to add | Partial |
| Ransomware / data loss | Encrypted, immutable backups with tested restore | Before launch |
| Client IP spoofing | Trusted-proxy list (`FORWARDED_ALLOW_IPS`); per-account limits don't depend on IP | ✅ Needs correct production proxy |

## Mandatory security scenarios

| # | Scenario | Covered by |
| --- | --- | --- |
| 1 | Org A user reads org B assets | `test_tenancy.py::test_user_cannot_read_another_organisations_asset`, RLS test |
| 2 | Agent forges organisation ID | `test_endpoints.py::test_forged_organisation_identifiers_are_rejected_or_ignored` |
| 3 | Agent enrols with expired token | `test_endpoints.py::test_tokens_are_single_use_and_expire` |
| 4 | Monitoring job reaches internal or metadata address | `test_assets.py::test_verification_refuses_internal_addresses`, `test_monitoring_rules.py::test_redirect_to_internal_address_is_refused` |
| 5 | Malformed telemetry | `test_endpoints.py::test_malformed_telemetry_is_rejected` |
| 6 | Download another org's report | Phase 5 (same tenant guard) |
| 7 | Revoked former employee | `test_removed_member_loses_access_immediately`, `test_suspended_member_loses_access` |
| 8 | Event burst | Phase 3 load tests |
| 9 | Unauthorised privilege escalation | `test_privilege_escalation_is_refused`, role matrix test |
| 10 | Backup restored into a clean environment | Before launch |
