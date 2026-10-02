"""Initial schema.

Revision ID: 001_initial
Revises:
Create Date: 2026-10-02
"""

from alembic import op

from app.models import Base

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=op.get_bind())
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_incident_embeddings_hnsw
        ON incident_embeddings USING hnsw (embedding vector_cosine_ops)
        """
    )
    op.execute(
        "INSERT INTO incident_counters (id, next_number) VALUES (1, 1024) "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
    op.execute("DROP EXTENSION IF EXISTS vector")
