"""Identity and tenancy. Incidents hang off workspaces, not off a global operator header."""

from datetime import datetime
from uuid import UUID as PyUUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UuidMixin, utcnow

ORG_ROLES = ("owner", "admin", "member")
WORKSPACE_ROLES = ("admin", "operator", "viewer", "auditor")
ORG_STATUSES = ("active", "suspended")
WORKSPACE_STATUSES = ("active", "archived")
USER_STATUSES = ("active", "disabled")


class Organization(UuidMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class Workspace(UuidMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_workspaces_org_slug"),)

    organization_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class User(UuidMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrganizationMember(UuidMixin, TimestampMixin, Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_members"),)

    organization_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)


class WorkspaceMember(UuidMixin, TimestampMixin, Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members"),)

    workspace_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, index=True
    )
    user_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)


class RefreshToken(UuidMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )


class IdentityProvider(UuidMixin, TimestampMixin, Base):
    __tablename__ = "identity_providers"
    __table_args__ = (UniqueConstraint("organization_id", "type", name="uq_idp_org_type"),)

    organization_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(400))
    client_id: Mapped[str | None] = mapped_column(String(200))
    client_secret_encrypted: Mapped[str | None] = mapped_column(String(2000))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class UserIdentity(UuidMixin, Base):
    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_user_identities_subject"),)

    user_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )


class WorkspaceApiKey(UuidMixin, Base):
    __tablename__ = "workspace_api_keys"

    workspace_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[PyUUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )


class WorkspaceIncidentCounter(Base):
    __tablename__ = "workspace_incident_counters"

    workspace_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspaces.id"), primary_key=True
    )
    next_number: Mapped[int] = mapped_column(Integer, nullable=False)


class WorkspaceIntegration(UuidMixin, TimestampMixin, Base):
    __tablename__ = "workspace_integrations"
    __table_args__ = (UniqueConstraint("workspace_id", "kind", name="uq_workspace_integrations_kind"),)

    workspace_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    public_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    has_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class IntegrationConnection(UuidMixin, TimestampMixin, Base):
    __tablename__ = "integration_connections"
    __table_args__ = (UniqueConstraint("workspace_id", "provider", name="uq_integration_connections_provider"),)

    workspace_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DISCONNECTED")
    encrypted_credentials: Mapped[str | None] = mapped_column(Text)
    configuration: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(400))
