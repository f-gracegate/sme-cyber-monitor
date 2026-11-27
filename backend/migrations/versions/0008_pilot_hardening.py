"""pilot and hardening: email verification, alert outcomes, suppression, feedback, retention,
organisation deletion and data exports

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-27 12:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_ORG = "current_setting('app.current_org', true)"
CURRENT_USER = "current_setting('app.current_user', true)"
BYPASS = "current_setting('app.rls_bypass', true) = 'on'"


def _enable(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def _ts(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _created() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.add_column("users", _ts("email_verified_at"))
    # Accounts that existed before verification was introduced are treated as verified.
    op.execute("UPDATE users SET email_verified_at = created_at")

    op.add_column("alerts", sa.Column("outcome", sa.String(20)))
    op.execute("UPDATE alerts SET outcome = 'fixed' WHERE status = 'resolved'")

    op.add_column(
        "organisations",
        sa.Column("telemetry_retention_days", sa.Integer(), nullable=False, server_default="30"),
    )
    op.add_column("organisations", _ts("deletion_requested_at"))
    op.add_column("organisations", sa.Column("deletion_requested_by", sa.UUID()))
    op.create_foreign_key(
        "fk_organisations_deletion_requested_by_users",
        "organisations",
        "users",
        ["deletion_requested_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("organisations", _ts("deletion_scheduled_for"))
    op.add_column("organisations", _ts("deleted_at"))

    op.create_table(
        "suppression_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organisation_id", sa.UUID(), nullable=False),
        sa.Column("rule_key", sa.String(64), nullable=False),
        sa.Column("asset_id", sa.UUID()),
        sa.Column("reason", sa.String(500), nullable=False),
        _ts("expires_at"),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        _ts("last_hit_at"),
        sa.Column("created_by", sa.UUID()),
        _created(),
        _ts("removed_at"),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_suppression_rules_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_suppression_rules_asset_id_assets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_suppression_rules_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppression_rules")),
    )
    op.create_index("ix_suppression_org_rule", "suppression_rules", ["organisation_id", "rule_key"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organisation_id", sa.UUID()),
        sa.Column("user_id", sa.UUID()),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("page", sa.String(200)),
        sa.Column("rating", sa.SmallInteger()),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        _created(),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_feedback_organisation_id_organisations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_feedback_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback")),
    )

    op.create_table(
        "data_exports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organisation_id", sa.UUID(), nullable=False),
        sa.Column("requested_by", sa.UUID()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("storage_key", sa.String(200)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("sha256", sa.String(64)),
        sa.Column("summary", sa.Text()),
        _created(),
        _ts("expires_at", nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_data_exports_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_data_exports_requested_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_exports")),
    )
    op.create_index("ix_data_exports_org", "data_exports", ["organisation_id"])

    for table in ("suppression_rules", "data_exports"):
        _enable(table)
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (organisation_id::text = {CURRENT_ORG} OR {BYPASS})"
        )
    # People see and write only their own feedback; the platform team reads it in system context.
    _enable("feedback")
    op.execute(
        f"CREATE POLICY own_feedback ON feedback USING (user_id::text = {CURRENT_USER} OR {BYPASS})"
    )
    role = os.environ.get("APP_DB_USER", "smecm_app")
    op.execute(f"REVOKE TRUNCATE ON feedback, suppression_rules, data_exports FROM {role}")


def downgrade() -> None:
    op.drop_table("data_exports")
    op.drop_table("feedback")
    op.drop_table("suppression_rules")
    op.drop_constraint(
        "fk_organisations_deletion_requested_by_users", "organisations", type_="foreignkey"
    )
    for col in (
        "deleted_at",
        "deletion_scheduled_for",
        "deletion_requested_by",
        "deletion_requested_at",
        "telemetry_retention_days",
    ):
        op.drop_column("organisations", col)
    op.drop_column("alerts", "outcome")
    op.drop_column("users", "email_verified_at")
