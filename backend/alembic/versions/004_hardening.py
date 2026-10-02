"""Workspace secret vault, execution reliability, stream tickets storage.

Revision ID: 004_hardening
Revises: 003_vertical_slice
Create Date: 2026-10-02
"""

from alembic import op
from sqlalchemy import inspect

revision = "004_hardening"
down_revision = "003_vertical_slice"
branch_labels = None
depends_on = None


def _run(sql: str) -> None:
    for statement in sql.split(";"):
        statement = statement.strip()
        if statement:
            op.execute(statement)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "integration_connections" not in tables:
        _run(
            """
            CREATE TABLE integration_connections (
                id UUID PRIMARY KEY,
                workspace_id UUID NOT NULL REFERENCES workspaces(id),
                provider VARCHAR(32) NOT NULL,
                display_name VARCHAR(120) NOT NULL,
                status VARCHAR(32) NOT NULL,
                encrypted_credentials TEXT,
                configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_by UUID REFERENCES users(id),
                last_verified_at TIMESTAMPTZ,
                last_error VARCHAR(400),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (workspace_id, provider)
            );
            CREATE INDEX ix_integration_connections_workspace
                ON integration_connections (workspace_id);
            """
        )

    action_cols = {col["name"] for col in inspect(bind).get_columns("incident_actions")}
    if "attempt_count" not in action_cols:
        _run(
            """
            ALTER TABLE incident_actions ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE incident_actions ADD COLUMN last_error TEXT;
            ALTER TABLE incident_actions ADD COLUMN retry_class VARCHAR(40);
            ALTER TABLE incident_actions ADD COLUMN provider_ref VARCHAR(200);
            ALTER TABLE incident_actions ADD COLUMN next_retry_at TIMESTAMPTZ;
            ALTER TABLE incident_actions ADD COLUMN idempotency_key VARCHAR(128)
            """
        )
    op.execute("ALTER TABLE incident_actions DROP CONSTRAINT IF EXISTS ck_actions_status")
    op.execute(
        """
        ALTER TABLE incident_actions ADD CONSTRAINT ck_actions_status CHECK (
            status IN (
                'PROPOSED','PENDING_APPROVAL','WAITING_APPROVAL','APPROVED','EXECUTING',
                'EXECUTED','SUCCEEDED','FAILED','CANCELLED','REJECTED'
            )
        )
        """
    )
    op.execute("ALTER TABLE approval_requests DROP CONSTRAINT IF EXISTS ck_approvals_status")
    op.execute(
        """
        ALTER TABLE approval_requests ADD CONSTRAINT ck_approvals_status CHECK (
            status IN ('PENDING_APPROVAL','APPROVED','REJECTED','EXPIRED','CANCELLED')
        )
        """
    )


def downgrade() -> None:
    raise RuntimeError("Hardening schema cannot be downgraded safely.")
