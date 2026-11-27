"""mobile, push notifications, billing and onboarding

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-27 09:00:00
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_ORG = "current_setting('app.current_org', true)"
CURRENT_USER = "current_setting('app.current_user', true)"
BYPASS = "current_setting('app.rls_bypass', true) = 'on'"


def _enable(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("last_reminder", sa.String(64), nullable=True))
    op.add_column(
        "organisations",
        sa.Column("onboarding_dismissed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "auth_sessions",
        sa.Column("client", sa.String(16), nullable=False, server_default="web"),
    )
    op.add_column("notifications", sa.Column("pushed_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_notifications_push_pending",
        "notifications",
        ["created_at"],
        postgresql_where=sa.text("pushed_at IS NULL"),
    )
    op.add_column(
        "notification_preferences",
        sa.Column("push_min_severity", sa.String(16), nullable=False, server_default="high"),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organisation_id", sa.UUID(), nullable=False),
        sa.Column("reference", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("plan_code", sa.String(32), nullable=False),
        sa.Column("billing_period", sa.String(16), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("failure_reason", sa.String(300)),
        sa.Column("provider_reference", sa.String(100)),
        sa.Column(
            "payment_method",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("receipt_number", sa.Integer()),
        sa.Column("credit_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period_start", sa.DateTime(timezone=True)),
        sa.Column("period_end", sa.DateTime(timezone=True)),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.UUID()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_payments_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_payments_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("reference", name=op.f("uq_payments_reference")),
    )
    op.create_index(op.f("ix_payments_organisation_id"), "payments", ["organisation_id"])
    op.create_index(
        "uq_payments_org_receipt",
        "payments",
        ["organisation_id", "receipt_number"],
        unique=True,
        postgresql_where=sa.text("receipt_number IS NOT NULL"),
    )

    op.create_table(
        "push_devices",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID()),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("device_name", sa.String(100)),
        sa.Column("app_version", sa.String(32)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_error", sa.String(200)),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_push_devices_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["auth_sessions.id"],
            name=op.f("fk_push_devices_session_id_auth_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_devices")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_push_devices_token_hash")),
    )
    op.create_index(op.f("ix_push_devices_user_id"), "push_devices", ["user_id"])

    _enable("payments")
    op.execute(
        "CREATE POLICY tenant_isolation ON payments "
        f"USING (organisation_id::text = {CURRENT_ORG} OR {BYPASS})"
    )
    # A phone belongs to the person signed in on it, not to an organisation.
    _enable("push_devices")
    op.execute(
        "CREATE POLICY owner_only ON push_devices "
        f"USING (user_id::text = {CURRENT_USER} OR {BYPASS})"
    )
    role = os.environ.get("APP_DB_USER", "smecm_app")
    # Paid payments are financial records: the application may record and update attempts but
    # never delete them.
    op.execute(f"REVOKE DELETE, TRUNCATE ON payments FROM {role}")


def downgrade() -> None:
    op.drop_table("push_devices")
    op.drop_table("payments")
    op.drop_column("notification_preferences", "push_min_severity")
    op.drop_index("ix_notifications_push_pending", table_name="notifications")
    op.drop_column("notifications", "pushed_at")
    op.drop_column("auth_sessions", "client")
    op.drop_column("organisations", "onboarding_dismissed_at")
    op.drop_column("subscriptions", "last_reminder")
