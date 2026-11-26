"""Role-based access control. Enforced in the API layer for every organisation-scoped request."""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    SECURITY_ANALYST = "security_analyst"
    IT_ADMIN = "it_admin"
    AUDITOR = "auditor"
    EMPLOYEE = "employee"
    EXECUTIVE = "executive"


ROLE_LABELS = {
    Role.OWNER: "Organisation Owner",
    Role.ADMIN: "Organisation Administrator",
    Role.SECURITY_ANALYST: "Security Analyst",
    Role.IT_ADMIN: "IT Administrator",
    Role.AUDITOR: "Auditor / Compliance Viewer",
    Role.EMPLOYEE: "Standard Employee",
    Role.EXECUTIVE: "Executive Viewer",
}


class Perm(StrEnum):
    ORG_READ = "org:read"
    ORG_UPDATE = "org:update"
    MEMBERS_READ = "members:read"
    MEMBERS_MANAGE = "members:manage"
    DEPARTMENTS_MANAGE = "departments:manage"
    ASSETS_READ = "assets:read"
    ASSETS_WRITE = "assets:write"
    ASSETS_VERIFY = "assets:verify"
    AUDIT_READ = "audit:read"
    BILLING_READ = "billing:read"
    BILLING_MANAGE = "billing:manage"
    REPORTS_READ = "reports:read"
    MONITORING_READ = "monitoring:read"
    MONITORING_MANAGE = "monitoring:manage"
    FINDINGS_READ = "findings:read"
    FINDINGS_MANAGE = "findings:manage"
    ALERTS_READ = "alerts:read"
    ALERTS_MANAGE = "alerts:manage"
    INCIDENTS_READ = "incidents:read"
    INCIDENTS_MANAGE = "incidents:manage"
    INCIDENTS_REPORT = "incidents:report"
    REMEDIATION_READ = "remediation:read"
    REMEDIATION_MANAGE = "remediation:manage"


_ALL = frozenset(Perm)

ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.OWNER: _ALL,
    Role.ADMIN: _ALL - {Perm.BILLING_MANAGE},
    Role.SECURITY_ANALYST: frozenset(
        {
            Perm.ORG_READ,
            Perm.MEMBERS_READ,
            Perm.ASSETS_READ,
            Perm.REPORTS_READ,
            Perm.MONITORING_READ,
            Perm.FINDINGS_READ,
            Perm.FINDINGS_MANAGE,
            Perm.ALERTS_READ,
            Perm.ALERTS_MANAGE,
            Perm.INCIDENTS_READ,
            Perm.INCIDENTS_MANAGE,
            Perm.INCIDENTS_REPORT,
            Perm.REMEDIATION_READ,
            Perm.REMEDIATION_MANAGE,
        }
    ),
    Role.IT_ADMIN: frozenset(
        {
            Perm.ORG_READ,
            Perm.MEMBERS_READ,
            Perm.ASSETS_READ,
            Perm.ASSETS_WRITE,
            Perm.ASSETS_VERIFY,
            Perm.REPORTS_READ,
            Perm.MONITORING_READ,
            Perm.MONITORING_MANAGE,
            Perm.FINDINGS_READ,
            Perm.FINDINGS_MANAGE,
            Perm.ALERTS_READ,
            Perm.ALERTS_MANAGE,
            Perm.INCIDENTS_READ,
            Perm.INCIDENTS_MANAGE,
            Perm.INCIDENTS_REPORT,
            Perm.REMEDIATION_READ,
            Perm.REMEDIATION_MANAGE,
        }
    ),
    Role.AUDITOR: frozenset(
        {
            Perm.ORG_READ,
            Perm.MEMBERS_READ,
            Perm.ASSETS_READ,
            Perm.AUDIT_READ,
            Perm.BILLING_READ,
            Perm.REPORTS_READ,
            Perm.MONITORING_READ,
            Perm.FINDINGS_READ,
            Perm.ALERTS_READ,
            Perm.INCIDENTS_READ,
            Perm.INCIDENTS_REPORT,
            Perm.REMEDIATION_READ,
        }
    ),
    Role.EMPLOYEE: frozenset({Perm.ORG_READ, Perm.INCIDENTS_REPORT}),
    Role.EXECUTIVE: frozenset(
        {
            Perm.ORG_READ,
            Perm.ASSETS_READ,
            Perm.REPORTS_READ,
            Perm.MONITORING_READ,
            Perm.FINDINGS_READ,
            Perm.ALERTS_READ,
            Perm.INCIDENTS_READ,
            Perm.INCIDENTS_REPORT,
            Perm.REMEDIATION_READ,
        }
    ),
}


def permissions_for(role: str) -> frozenset[Perm]:
    try:
        return ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return frozenset()


def can_assign_role(actor_role: str, target_role: str) -> bool:
    """Only owners can grant or remove the owner role. Admins manage every other role."""
    if actor_role == Role.OWNER:
        return True
    if actor_role == Role.ADMIN:
        return target_role != Role.OWNER
    return False
