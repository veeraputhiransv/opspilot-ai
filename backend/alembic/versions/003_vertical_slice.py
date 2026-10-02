"""Vertical slice: evidence, ingest idempotency, RCA versions, execution guards.

Revision ID: 003_vertical_slice
Revises: 002_identity_and_tenancy
Create Date: 2026-10-02
"""

from alembic import op
from sqlalchemy import inspect

revision = "003_vertical_slice"
down_revision = "002_identity_and_tenancy"
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
    event_cols = {col["name"] for col in inspect(bind).get_columns("incident_events")}
    if "workspace_id" not in event_cols:
        _run(
            """
            ALTER TABLE incident_events ADD COLUMN workspace_id UUID;
            UPDATE incident_events e
            SET workspace_id = i.workspace_id
            FROM incidents i
            WHERE i.id = e.incident_id;
            ALTER TABLE incident_events ALTER COLUMN workspace_id SET NOT NULL;
            ALTER TABLE incident_events
                ADD CONSTRAINT fk_incident_events_workspace
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id);
            ALTER TABLE incident_events ADD COLUMN idempotency_key VARCHAR(128);
            UPDATE incident_events SET idempotency_key = id::text WHERE idempotency_key IS NULL;
            ALTER TABLE incident_events ALTER COLUMN idempotency_key SET NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_events_workspace_idempotency
                ON incident_events (workspace_id, idempotency_key);
            """
        )

    if "incident_evidence" not in tables:
        _run(
            """
            CREATE TABLE incident_evidence (
                id UUID PRIMARY KEY,
                workspace_id UUID NOT NULL REFERENCES workspaces(id),
                incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                source_type VARCHAR(64) NOT NULL,
                source_reference VARCHAR(200),
                title VARCHAR(200) NOT NULL,
                summary TEXT NOT NULL,
                observed_at TIMESTAMPTZ,
                metadata JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX ix_evidence_incident ON incident_evidence (incident_id, created_at);
            CREATE INDEX ix_evidence_workspace ON incident_evidence (workspace_id, created_at);
            """
        )

    hyp_cols = {col["name"] for col in inspect(bind).get_columns("incident_hypotheses")}
    if "evidence_ids" not in hyp_cols:
        _run(
            "ALTER TABLE incident_hypotheses ADD COLUMN evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb"
        )

    action_cols = {col["name"] for col in inspect(bind).get_columns("incident_actions")}
    if "execution_id" not in action_cols:
        _run(
            """
            ALTER TABLE incident_actions ADD COLUMN execution_id UUID;
            ALTER TABLE incident_actions ADD COLUMN executed_at TIMESTAMPTZ;
            CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_actions_execution_id
                ON incident_actions (execution_id) WHERE execution_id IS NOT NULL;
            """
        )

    approval_cols = {col["name"] for col in inspect(bind).get_columns("approval_requests")}
    if "workspace_id" not in approval_cols:
        _run(
            """
            ALTER TABLE approval_requests ADD COLUMN workspace_id UUID;
            UPDATE approval_requests a
            SET workspace_id = i.workspace_id
            FROM incidents i
            WHERE i.id = a.incident_id;
            ALTER TABLE approval_requests ALTER COLUMN workspace_id SET NOT NULL;
            ALTER TABLE approval_requests
                ADD CONSTRAINT fk_approvals_workspace
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id);
            ALTER TABLE approval_requests ADD COLUMN agent_run_id UUID REFERENCES agent_runs(id);
            ALTER TABLE approval_requests ADD COLUMN decided_by VARCHAR(120);
            ALTER TABLE approval_requests ADD COLUMN decided_at TIMESTAMPTZ;
            ALTER TABLE approval_requests ADD COLUMN decision_reason TEXT;
            """
        )

    rca_cols = {col["name"] for col in inspect(bind).get_columns("rca_reports")}
    if "version" not in rca_cols:
        _run(
            """
            ALTER TABLE rca_reports ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE rca_reports ADD COLUMN disclosure TEXT NOT NULL DEFAULT
                'This RCA was assembled by OpsPilot from persisted incident facts and evidence. Hypothesis scores are deterministic investigation scores, not calibrated probabilities.';
            ALTER TABLE rca_reports DROP CONSTRAINT IF EXISTS rca_reports_incident_id_key;
            CREATE UNIQUE INDEX IF NOT EXISTS uq_rca_incident_version
                ON rca_reports (incident_id, version);
            """
        )

    if "workspace_integrations" not in tables:
        _run(
            """
            CREATE TABLE workspace_integrations (
                id UUID PRIMARY KEY,
                workspace_id UUID NOT NULL REFERENCES workspaces(id),
                kind VARCHAR(32) NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT false,
                public_config JSONB NOT NULL DEFAULT '{}'::jsonb,
                has_credentials BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (workspace_id, kind)
            );
            """
        )


def downgrade() -> None:
    raise RuntimeError("Vertical slice schema cannot be downgraded safely.")
