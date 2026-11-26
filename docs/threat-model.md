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
| SSRF via ownership checks | Public-IP-only resolution, pinned connection, no redirects, tiny reads, timeouts | ✅ (monitoring workers will add an egress proxy) |
| Monitoring someone else's site | Websites and domains need DNS or file proof of control | ✅ |
| Audit tampering | App role cannot UPDATE/DELETE audit rows | ✅ |
| Open redirect after login | `next` parameter restricted to same-site paths | ✅ |
| Malicious agent / telemetry poisoning | Device identity, short-lived enrolment tokens, schema validation, tenant derived from enrolment | Phase 3 |
| Alert flooding | Deduplication, grouping, suppression, rate controls | Phase 5 |
| Credential theft (integrations) | Encrypted secrets, rotation, never re-displayed | Phase 3+ |
| Supply chain | Locked dependencies, CI checks; image scanning and signed agent packages to add | Partial |
| Ransomware / data loss | Encrypted, immutable backups with tested restore | Before launch |
| Client IP spoofing | Trusted-proxy list (`FORWARDED_ALLOW_IPS`); per-account limits don't depend on IP | ✅ Needs correct production proxy |

## Mandatory security scenarios

| # | Scenario | Covered by |
| --- | --- | --- |
| 1 | Org A user reads org B assets | `test_tenancy.py::test_user_cannot_read_another_organisations_asset`, RLS test |
| 2 | Agent forges organisation ID | Phase 3 (design: tenant from enrolment) |
| 3 | Agent enrols with expired token | Phase 3 |
| 4 | Monitoring job reaches internal or metadata address | `test_assets.py::test_verification_refuses_internal_addresses` |
| 5 | Malformed telemetry | Phase 3 |
| 6 | Download another org's report | Phase 5 (same tenant guard) |
| 7 | Revoked former employee | `test_removed_member_loses_access_immediately`, `test_suspended_member_loses_access` |
| 8 | Event burst | Phase 3 load tests |
| 9 | Unauthorised privilege escalation | `test_privilege_escalation_is_refused`, role matrix test |
| 10 | Backup restored into a clean environment | Before launch |
