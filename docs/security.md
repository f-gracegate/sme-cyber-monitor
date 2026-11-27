# Security testing and hardening (Phase 7)

The product plan's release rule: **no unresolved critical security vulnerabilities, no known
cross-tenant access flaws and no untested backup recovery procedure at commercial launch.**

| Release condition | Status |
| --- | --- |
| No known cross-tenant access flaws | ✅ Independent code review found none. Covered by RLS, membership checks and the tenancy tests |
| No unresolved critical vulnerabilities | ✅ None from the review or the scanners. All review findings below are fixed |
| Tested backup recovery | ✅ Restore drill runs in CI on every push (see [operations.md](operations.md)) |
| External penetration test | ⏳ Owner task before launch: commission a test of the production deployment |

## Pre-launch code review

An independent read of the backend looked for cross-tenant access, authentication and session
flaws, CSRF, privilege escalation, injection, path traversal, SSRF, payment tampering, rate-limit
gaps and missing audit logging. It confirmed the following controls are sound: tenant isolation
(RLS forced on every tenant table, membership checked first), role changes, token typing and
rotation, CSRF, TOTP replay protection, Paystack verification, storage key handling, SSRF pinning
and device credentials.

It found these issues, all fixed in Phase 7 with tests in `tests/test_hardening.py`:

| Finding | Fix |
| --- | --- |
| A missing `ENVIRONMENT` fell back to development, which turned on the dev mailbox and sandbox payments | Default is now `production`. Unset or unsafe settings refuse to start, and SMTP is required outside development |
| Re-enrolment revived revoked devices and could take over enrolled ones | A known machine can't enrol again until an admin clicks **Allow re-enrolment**. Enrolment tokens are row-locked |
| MFA codes could be brute-forced, and failures didn't count towards lockout | Wrong codes count towards the lockout. Each sign-in attempt allows 5 codes and can only be completed once. Sign-in rate limits fail closed if Redis is down |
| Account pre-hijacking (no email verification) | Email verification before creating a workspace. A reset on an unverified account clears any MFA and ends all sessions |
| Push tokens could be claimed by another account | A token moves to a new account only after the previous owner's session on that phone has ended |
| Monitoring followed redirects to any host or port | Only same-site redirects on ports 80/443 are followed, and redirects to internal addresses are still flagged |
| Plan limits bypassed by Wazuh-created assets and enrolment of lapsed organisations | Plan and subscription checks apply there too |
| RLS-bypass blocks flushed the whole request's changes | The request's own changes are flushed under RLS before the bypass |
| No limits on evidence uploads or incident creation | Per-person rate limits, and a 2 GB evidence quota per organisation |
| MFA off and password reset left other sessions or links active | Other sessions end. Outstanding reset links are invalidated |
| Lockout response revealed which accounts exist | Unknown accounts lock exactly like real ones |
| Staff could see organisation-wide security detail on the overview | Staff get a simple "report it" overview without scores, findings or MFA coverage |

Accepted as-is: registration says when an email address is already in use (common practice,
and rate-limited).

## Automated scanning (CI `security` job)

- `pip-audit` against the hash-pinned `backend/requirements.lock`.
- `npm audit --omit=dev --audit-level=high` for the web app.
- `gitleaks` over the full history for committed secrets.
- Trivy over the repository: dependency vulnerabilities, Dockerfile and Compose
  misconfiguration, and secrets (HIGH and CRITICAL fail the build).
- Dependabot opens weekly update pull requests for pip, npm, pub, Docker and Actions.

Python installs use `pip install --require-hashes` from the lock files. To change a dependency,
edit `requirements.txt` and regenerate:

```bash
docker compose run --rm -u root -v "$PWD/backend:/app" backend sh -c \
  "pip install pip-tools && pip-compile --generate-hashes --allow-unsafe -o requirements.lock requirements.txt \
   && pip-compile --generate-hashes --allow-unsafe -o requirements-dev.lock requirements-dev.txt"
```

## Mandatory security scenarios

All ten scenarios from the product plan are now automated (see
[threat-model.md](threat-model.md)). Scenario 8 (event burst) is in the load test, and
scenario 10 (restore into a clean environment) is the restore drill.

## Before launch (owner)

- A penetration test of the production deployment by an independent firm. Give them
  `docs/threat-model.md` and two test organisations.
- Signed agent and collector packages (code-signing certificates for Windows and macOS).
- A security contact (`security@` mailbox and a `/.well-known/security.txt`) and a responsible
  disclosure policy.
