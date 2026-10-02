"""Identity and workspace tenancy.

Revision ID: 002_identity_and_tenancy
Revises: 001_initial
Create Date: 2026-10-02
"""

from alembic import op
from sqlalchemy import inspect

revision = "002_identity_and_tenancy"
down_revision = "001_initial"
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
    if "organizations" not in tables:
        _run(
            """
            CREATE TABLE organizations (
                id UUID PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                slug VARCHAR(80) NOT NULL UNIQUE,
                status VARCHAR(32) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE TABLE workspaces (
                id UUID PRIMARY KEY,
                organization_id UUID NOT NULL REFERENCES organizations(id),
                name VARCHAR(120) NOT NULL,
                slug VARCHAR(80) NOT NULL,
                status VARCHAR(32) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (organization_id, slug)
            );
            CREATE INDEX ix_workspaces_organization_id ON workspaces (organization_id);
            CREATE TABLE users (
                id UUID PRIMARY KEY,
                email VARCHAR(320) NOT NULL UNIQUE,
                password_hash VARCHAR(255),
                full_name VARCHAR(120) NOT NULL,
                status VARCHAR(32) NOT NULL,
                email_verified_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE TABLE organization_members (
                id UUID PRIMARY KEY,
                organization_id UUID NOT NULL REFERENCES organizations(id),
                user_id UUID NOT NULL REFERENCES users(id),
                role VARCHAR(32) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (organization_id, user_id)
            );
            CREATE TABLE workspace_members (
                id UUID PRIMARY KEY,
                workspace_id UUID NOT NULL REFERENCES workspaces(id),
                user_id UUID NOT NULL REFERENCES users(id),
                role VARCHAR(32) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (workspace_id, user_id)
            );
            CREATE TABLE refresh_tokens (
                id UUID PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id),
                token_hash VARCHAR(64) NOT NULL UNIQUE,
                expires_at TIMESTAMPTZ NOT NULL,
                revoked_at TIMESTAMPTZ,
                user_agent VARCHAR(200),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id);
            CREATE TABLE identity_providers (
                id UUID PRIMARY KEY,
                organization_id UUID NOT NULL REFERENCES organizations(id),
                type VARCHAR(32) NOT NULL,
                issuer VARCHAR(400),
                client_id VARCHAR(200),
                client_secret_encrypted VARCHAR(2000),
                enabled BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (organization_id, type)
            );
            CREATE TABLE user_identities (
                id UUID PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id),
                provider VARCHAR(32) NOT NULL,
                subject VARCHAR(255) NOT NULL,
                email VARCHAR(320),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (provider, subject)
            );
            CREATE TABLE workspace_api_keys (
                id UUID PRIMARY KEY,
                workspace_id UUID NOT NULL REFERENCES workspaces(id),
                name VARCHAR(80) NOT NULL,
                key_prefix VARCHAR(16) NOT NULL,
                key_hash VARCHAR(64) NOT NULL UNIQUE,
                scopes JSONB NOT NULL,
                last_used_at TIMESTAMPTZ,
                revoked_at TIMESTAMPTZ,
                created_by_user_id UUID REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE TABLE workspace_incident_counters (
                workspace_id UUID PRIMARY KEY REFERENCES workspaces(id),
                next_number INTEGER NOT NULL
            );
            """
        )

    incident_cols = {col["name"] for col in inspect(bind).get_columns("incidents")}
    if "workspace_id" not in incident_cols:
        _run(
            """
            INSERT INTO organizations (id, name, slug, status)
            SELECT '00000000-0000-4000-8000-000000000001', 'Local', 'local', 'active'
            WHERE NOT EXISTS (SELECT 1 FROM organizations WHERE slug = 'local');

            INSERT INTO workspaces (id, organization_id, name, slug, status)
            SELECT '00000000-0000-4000-8000-000000000002',
                   (SELECT id FROM organizations WHERE slug = 'local'),
                   'Production', 'production', 'active'
            WHERE NOT EXISTS (
                SELECT 1 FROM workspaces WHERE id = '00000000-0000-4000-8000-000000000002'
            );

            ALTER TABLE incidents ADD COLUMN organization_id UUID;
            ALTER TABLE incidents ADD COLUMN workspace_id UUID;
            UPDATE incidents SET
                organization_id = '00000000-0000-4000-8000-000000000001',
                workspace_id = '00000000-0000-4000-8000-000000000002'
            WHERE workspace_id IS NULL;
            ALTER TABLE incidents ALTER COLUMN organization_id SET NOT NULL;
            ALTER TABLE incidents ALTER COLUMN workspace_id SET NOT NULL;
            ALTER TABLE incidents
                ADD CONSTRAINT fk_incidents_organization
                FOREIGN KEY (organization_id) REFERENCES organizations(id);
            ALTER TABLE incidents
                ADD CONSTRAINT fk_incidents_workspace
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id);
            ALTER TABLE incidents DROP CONSTRAINT IF EXISTS incidents_incident_number_key;
            CREATE UNIQUE INDEX IF NOT EXISTS uq_incidents_workspace_number
                ON incidents (workspace_id, incident_number);
            CREATE INDEX IF NOT EXISTS ix_incidents_workspace_status ON incidents (workspace_id, status);
            """
        )
        _run(
            """
            INSERT INTO workspace_incident_counters (workspace_id, next_number)
            SELECT '00000000-0000-4000-8000-000000000002', COALESCE(MAX(next_number), 1024)
            FROM incident_counters
            ON CONFLICT (workspace_id) DO NOTHING
            """
        )

    knowledge_cols = {col["name"] for col in inspect(bind).get_columns("knowledge_documents")}
    if "workspace_id" not in knowledge_cols:
        _run(
            """
            ALTER TABLE knowledge_documents ADD COLUMN workspace_id UUID;
            ALTER TABLE knowledge_documents ADD COLUMN source_type VARCHAR(32) DEFAULT 'prior_incident';
            UPDATE knowledge_documents SET
                workspace_id = '00000000-0000-4000-8000-000000000002',
                source_type = 'prior_incident'
            WHERE workspace_id IS NULL;
            ALTER TABLE knowledge_documents ALTER COLUMN workspace_id SET NOT NULL;
            ALTER TABLE knowledge_documents ALTER COLUMN source_type SET NOT NULL;
            ALTER TABLE knowledge_documents
                ADD CONSTRAINT fk_knowledge_workspace
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id);
            ALTER TABLE knowledge_documents DROP CONSTRAINT IF EXISTS knowledge_documents_external_id_key;
            CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_workspace_external
                ON knowledge_documents (workspace_id, external_id);
            """
        )

    report_cols = {col["name"] for col in inspect(bind).get_columns("customer_reports")}
    if "workspace_id" not in report_cols:
        _run(
            """
            ALTER TABLE customer_reports ADD COLUMN workspace_id UUID;
            UPDATE customer_reports SET workspace_id = '00000000-0000-4000-8000-000000000002'
            WHERE workspace_id IS NULL;
            ALTER TABLE customer_reports ALTER COLUMN workspace_id SET NOT NULL;
            ALTER TABLE customer_reports
                ADD CONSTRAINT fk_customer_reports_workspace
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id);
            ALTER TABLE customer_reports DROP CONSTRAINT IF EXISTS customer_reports_external_ref_key;
            CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_reports_workspace_ref
                ON customer_reports (workspace_id, external_ref);
            """
        )

    audit_cols = {col["name"] for col in inspect(bind).get_columns("audit_logs")}
    if "workspace_id" not in audit_cols:
        _run(
            """
            ALTER TABLE audit_logs ADD COLUMN organization_id UUID REFERENCES organizations(id);
            ALTER TABLE audit_logs ADD COLUMN workspace_id UUID REFERENCES workspaces(id);
            ALTER TABLE audit_logs ADD COLUMN actor_user_id UUID REFERENCES users(id);
            ALTER TABLE audit_logs ADD COLUMN actor_api_key_id UUID REFERENCES workspace_api_keys(id);
            ALTER TABLE audit_logs ADD COLUMN actor_type VARCHAR(32) NOT NULL DEFAULT 'system';
            CREATE INDEX IF NOT EXISTS ix_audit_workspace_time ON audit_logs (workspace_id, created_at);
            """
        )

    decision_cols = {col["name"] for col in inspect(bind).get_columns("approval_decisions")}
    if "actor_user_id" not in decision_cols:
        _run(
            "ALTER TABLE approval_decisions ADD COLUMN actor_user_id UUID REFERENCES users(id)"
        )


def downgrade() -> None:
    raise RuntimeError("Identity tenancy cannot be downgraded safely.")
