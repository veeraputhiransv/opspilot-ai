"""Immutable audit rows with redacted metadata."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redaction import redact
from app.identity.context import AuthContext
from app.models import AuditLog


def audit_row(
    *,
    auth: AuthContext | None,
    action: str,
    resource_type: str,
    resource_id: UUID | None = None,
    incident_id: UUID | None = None,
    detail: dict | None = None,
    actor: str | None = None,
) -> AuditLog:
    safe = None
    if detail:
        blocked = ("secret", "token", "password", "credential")
        safe = {
            key: redact(str(value))
            for key, value in detail.items()
            if not any(word in key.lower() for word in blocked)
        }
    return AuditLog(
        organization_id=auth.organization_id if auth else None,
        workspace_id=auth.workspace_id if auth else None,
        actor_user_id=auth.user_id if auth else None,
        actor_type=auth.via if auth else "system",
        incident_id=incident_id,
        actor=actor or (auth.actor_label if auth else "system"),
        action=action[:80],
        resource_type=resource_type[:64],
        resource_id=resource_id,
        detail=safe,
    )


async def record(session: AsyncSession, row: AuditLog) -> None:
    session.add(row)
