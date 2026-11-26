"""Row-Level Security: a second, database-enforced tenant boundary.

The API already scopes every query to the caller's organisation. These policies make sure
that even a missed filter cannot return another organisation's rows to the application role.

Revision ID: 0002
Revises: 0001
"""

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = os.environ.get("APP_DB_USER", "smecm_app")

CURRENT_ORG = "current_setting('app.current_org', true)"
CURRENT_USER = "current_setting('app.current_user', true)"
BYPASS = "current_setting('app.rls_bypass', true) = 'on'"

TENANT_TABLES = ("departments", "invitations", "subscriptions", "assets", "asset_authorisations")


def _enable(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    for table in TENANT_TABLES:
        _enable(table)
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (organisation_id::text = {CURRENT_ORG} OR {BYPASS})"
        )

    # Users can always see their own memberships (to list their organisations), but can only
    # create or change memberships inside the organisation currently in context.
    _enable("memberships")
    op.execute(
        "CREATE POLICY tenant_isolation ON memberships "
        f"USING (organisation_id::text = {CURRENT_ORG} OR user_id::text = {CURRENT_USER} "
        f"OR {BYPASS}) "
        f"WITH CHECK (organisation_id::text = {CURRENT_ORG} OR {BYPASS})"
    )

    _enable("organisations")
    op.execute(
        "CREATE POLICY tenant_isolation ON organisations "
        f"USING (id::text = {CURRENT_ORG} OR {BYPASS} OR EXISTS ("
        "  SELECT 1 FROM memberships m WHERE m.organisation_id = organisations.id"
        f"  AND m.user_id::text = {CURRENT_USER} AND m.status = 'active')) "
        f"WITH CHECK (id::text = {CURRENT_ORG} OR {BYPASS})"
    )

    # Platform-level entries (no organisation) are visible only to the user they concern.
    _enable("audit_logs")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_logs "
        f"USING (organisation_id::text = {CURRENT_ORG} OR {BYPASS} "
        f"OR (organisation_id IS NULL AND actor_id::text = {CURRENT_USER}))"
    )
    # The audit trail is append-only for the application.
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"GRANT UPDATE, DELETE ON audit_logs TO {APP_ROLE}")
    for table in (*TENANT_TABLES, "memberships", "organisations", "audit_logs"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
