"""Register, login, refresh, workspace switch, ingest API keys."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, OpsPilotError, UnauthorizedError
from app.db import session_scope
from app.identity.context import VIEWER_ROLES, AuthContext
from app.identity.passwords import hash_password, verify_password
from app.identity.tokens import (
    decode_access_token,
    encode_access_token,
    hash_refresh_token,
    new_refresh_token,
)
from app.models import AuditLog
from app.models.base import utcnow
from app.models.identity import (
    Organization,
    OrganizationMember,
    RefreshToken,
    User,
    UserIdentity,
    Workspace,
    WorkspaceApiKey,
    WorkspaceIncidentCounter,
    WorkspaceMember,
)
from app.seed.constants import DEMO_USER_EMAIL, DEMO_WORKSPACE_SLUG, is_demo_workspace
from app.seed.demo import require_demo_seed

_SLUG = re.compile(r"[^a-z0-9]+")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user_id: UUID
    organization_id: UUID
    workspace_id: UUID
    roles: list[str]


class AuthService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self.sessions = sessions
        self.settings = settings

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        organization_name: str | None,
        user_agent: str | None,
    ) -> TokenPair:
        _validate_password(password)
        normalized = email.strip().lower()
        if _EMAIL.fullmatch(normalized) is None:
            raise OpsPilotError("Email is invalid.")
        name = full_name.strip()
        if len(name) < 2:
            raise OpsPilotError("Name is required.")
        org_name = (organization_name or f"{name}'s organization").strip()[:120]
        async with session_scope(self.sessions) as session:
            existing = await session.scalar(select(User).where(User.email == normalized))
            if existing is not None:
                raise ConflictError("An account with that email already exists.")
            user = User(
                email=normalized,
                password_hash=hash_password(password),
                full_name=name,
                status="active",
            )
            session.add(user)
            await session.flush()
            org = Organization(
                name=org_name,
                slug=await _unique_slug(session, Organization, slugify(org_name)),
                status="active",
            )
            session.add(org)
            await session.flush()
            workspace = Workspace(
                organization_id=org.id,
                name="Production",
                slug="production",
                status="active",
            )
            session.add(workspace)
            await session.flush()
            session.add(OrganizationMember(organization_id=org.id, user_id=user.id, role="owner"))
            session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin"))
            session.add(WorkspaceIncidentCounter(workspace_id=workspace.id, next_number=1024))
            session.add(
                UserIdentity(
                    user_id=user.id,
                    provider="password",
                    subject=str(user.id),
                    email=normalized,
                )
            )
            pair = await self._issue(session, user, org.id, workspace.id, ["admin"], user_agent)
            session.add(
                AuditLog(
                    organization_id=org.id,
                    workspace_id=workspace.id,
                    actor_user_id=user.id,
                    actor_type="jwt",
                    actor=user.email,
                    action="user_registered",
                    resource_type="user",
                    resource_id=user.id,
                )
            )
        return pair

    async def login(self, *, email: str, password: str, user_agent: str | None) -> TokenPair:
        normalized = email.strip().lower()
        async with session_scope(self.sessions) as session:
            user = await session.scalar(select(User).where(User.email == normalized))
            if user is None or user.password_hash is None or user.status != "active":
                raise UnauthorizedError("Email or password is incorrect.")
            if not verify_password(password, user.password_hash):
                raise UnauthorizedError("Email or password is incorrect.")
            membership = await session.scalar(
                select(WorkspaceMember)
                .where(WorkspaceMember.user_id == user.id)
                .order_by(WorkspaceMember.created_at)
            )
            if membership is None:
                raise ForbiddenError("This account has no workspace.")
            workspace = await session.get(Workspace, membership.workspace_id)
            if workspace is None:
                raise ForbiddenError("This account has no workspace.")
            pair = await self._issue(
                session,
                user,
                workspace.organization_id,
                workspace.id,
                [membership.role],
                user_agent,
            )
            session.add(
                AuditLog(
                    organization_id=workspace.organization_id,
                    workspace_id=workspace.id,
                    actor_user_id=user.id,
                    actor_type="jwt",
                    actor=user.email,
                    action="user_login",
                    resource_type="user",
                    resource_id=user.id,
                )
            )
            return pair

    async def demo_login(self, user_agent: str | None) -> TokenPair:
        require_demo_seed(self.settings)
        async with session_scope(self.sessions) as session:
            user = await session.scalar(select(User).where(User.email == DEMO_USER_EMAIL))
            if user is None or user.status != "active":
                raise ForbiddenError("The AcmeFlow demo workspace has not been seeded.")
            membership = await session.scalar(
                select(WorkspaceMember)
                .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
                .where(
                    WorkspaceMember.user_id == user.id,
                    Workspace.slug == DEMO_WORKSPACE_SLUG,
                )
            )
            if membership is None:
                raise ForbiddenError("The AcmeFlow demo workspace has not been seeded.")
            workspace = await session.get(Workspace, membership.workspace_id)
            if workspace is None:
                raise ForbiddenError("The AcmeFlow demo workspace has not been seeded.")
            pair = await self._issue(
                session,
                user,
                workspace.organization_id,
                workspace.id,
                [membership.role],
                user_agent,
            )
            session.add(
                AuditLog(
                    organization_id=workspace.organization_id,
                    workspace_id=workspace.id,
                    actor_user_id=user.id,
                    actor_type="jwt",
                    actor=user.email,
                    action="demo_session_started",
                    resource_type="user",
                    resource_id=user.id,
                )
            )
            return pair

    async def refresh(self, raw_token: str, user_agent: str | None) -> TokenPair:
        token_hash = hash_refresh_token(raw_token)
        async with session_scope(self.sessions) as session:
            row = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
            now = utcnow()
            if row is None or row.revoked_at is not None or row.expires_at <= now:
                raise UnauthorizedError("Refresh token is invalid or expired.")
            row.revoked_at = now
            user = await session.get(User, row.user_id)
            if user is None or user.status != "active":
                raise UnauthorizedError("Refresh token is invalid or expired.")
            membership = await session.scalar(
                select(WorkspaceMember)
                .where(WorkspaceMember.user_id == user.id)
                .order_by(WorkspaceMember.created_at)
            )
            if membership is None:
                raise ForbiddenError("This account has no workspace.")
            workspace = await session.get(Workspace, membership.workspace_id)
            if workspace is None:
                raise ForbiddenError("This account has no workspace.")
            return await self._issue(
                session,
                user,
                workspace.organization_id,
                workspace.id,
                [membership.role],
                user_agent,
            )

    async def logout(self, raw_token: str) -> None:
        token_hash = hash_refresh_token(raw_token)
        async with session_scope(self.sessions) as session:
            row = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
            if row is not None and row.revoked_at is None:
                row.revoked_at = utcnow()

    async def switch_workspace(self, user_id: UUID, workspace_id: UUID, user_agent: str | None) -> TokenPair:
        async with session_scope(self.sessions) as session:
            user = await session.get(User, user_id)
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.user_id == user_id,
                    WorkspaceMember.workspace_id == workspace_id,
                )
            )
            workspace = await session.get(Workspace, workspace_id)
            if user is None or membership is None or workspace is None:
                raise NotFoundError("Workspace not found.")
            pair = await self._issue(
                session,
                user,
                workspace.organization_id,
                workspace.id,
                [membership.role],
                user_agent,
            )
            session.add(
                AuditLog(
                    organization_id=workspace.organization_id,
                    workspace_id=workspace.id,
                    actor_user_id=user.id,
                    actor_type="jwt",
                    actor=user.email,
                    action="workspace_switch",
                    resource_type="workspace",
                    resource_id=workspace.id,
                )
            )
            return pair

    async def me(self, user_id: UUID) -> dict:
        async with session_scope(self.sessions) as session:
            user = await session.get(User, user_id)
            if user is None:
                raise UnauthorizedError("Not authenticated.")
            org_rows = (
                await session.execute(
                    select(OrganizationMember, Organization)
                    .join(Organization, Organization.id == OrganizationMember.organization_id)
                    .where(OrganizationMember.user_id == user_id)
                )
            ).all()
            ws_rows = (
                await session.execute(
                    select(WorkspaceMember, Workspace)
                    .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
                    .where(WorkspaceMember.user_id == user_id)
                )
            ).all()
            demo = any(
                is_demo_workspace(
                    next((org.slug for _member, org in org_rows if org.id == workspace.organization_id), None),
                    workspace.slug,
                )
                for _member, workspace in ws_rows
            )
            return {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "title": "Incident Commander" if user.email == DEMO_USER_EMAIL else None,
                "demo": demo,
                "organizations": [
                    {
                        "id": str(org.id),
                        "name": org.name,
                        "slug": org.slug,
                        "role": member.role,
                    }
                    for member, org in org_rows
                ],
                "workspaces": [
                    {
                        "id": str(workspace.id),
                        "organization_id": str(workspace.organization_id),
                        "name": workspace.name,
                        "slug": workspace.slug,
                        "role": member.role,
                    }
                    for member, workspace in ws_rows
                ],
            }

    def decode_bearer(self, token: str) -> dict:
        return decode_access_token(token, self.settings.jwt_secret)

    async def context_from_access_token(self, token: str) -> AuthContext:
        payload = self.decode_bearer(token)
        try:
            user_id = UUID(str(payload["sub"]))
            organization_id = UUID(str(payload["org"]))
            workspace_id = UUID(str(payload["ws"]))
        except (KeyError, ValueError) as exc:
            raise UnauthorizedError("Access token is invalid or expired.") from exc
        roles = tuple(str(role) for role in payload.get("roles") or [])
        if not any(role in VIEWER_ROLES for role in roles):
            raise ForbiddenError("This token cannot access the workspace.")
        async with session_scope(self.sessions) as session:
            user = await session.get(User, user_id)
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.user_id == user_id,
                    WorkspaceMember.workspace_id == workspace_id,
                )
            )
            workspace = await session.get(Workspace, workspace_id)
            organization = await session.get(Organization, organization_id)
            if user is None or user.status != "active" or membership is None or workspace is None:
                raise UnauthorizedError("Access token is invalid or expired.")
            return AuthContext(
                user_id=user_id,
                organization_id=organization_id,
                workspace_id=workspace_id,
                roles=(membership.role,),
                actor_label=user.email,
                via="jwt",
                is_demo_workspace=is_demo_workspace(
                    organization.slug if organization else None,
                    workspace.slug,
                ),
            )

    async def context_from_api_key(self, raw_key: str) -> AuthContext:
        if not raw_key.startswith("ops_live_"):
            raise UnauthorizedError("API key is invalid.")
        key_hash = sha256(raw_key.encode("utf-8")).hexdigest()
        async with session_scope(self.sessions) as session:
            row = await session.scalar(
                select(WorkspaceApiKey).where(WorkspaceApiKey.key_hash == key_hash)
            )
            if row is None or row.revoked_at is not None:
                raise UnauthorizedError("API key is invalid.")
            if "events:write" not in (row.scopes or []):
                raise ForbiddenError("This API key cannot ingest events.")
            workspace = await session.get(Workspace, row.workspace_id)
            if workspace is None:
                raise UnauthorizedError("API key is invalid.")
            organization = await session.get(Organization, workspace.organization_id)
            row.last_used_at = utcnow()
            return AuthContext(
                user_id=None,
                organization_id=workspace.organization_id,
                workspace_id=workspace.id,
                roles=("operator",),
                actor_label=f"api-key:{row.key_prefix}",
                via="api_key",
                is_demo_workspace=is_demo_workspace(
                    organization.slug if organization else None,
                    workspace.slug,
                ),
            )

    async def create_ingest_key(self, auth: AuthContext, name: str) -> str:
        if auth.is_demo_workspace:
            raise ForbiddenError("Demo sessions cannot create ingest keys.")
        if "admin" not in auth.roles:
            raise ForbiddenError("Only workspace admins can create ingest keys.")
        raw = f"ops_live_{token_urlsafe(32)}"
        async with session_scope(self.sessions) as session:
            session.add(
                WorkspaceApiKey(
                    workspace_id=auth.workspace_id,
                    name=name.strip()[:80] or "Ingest",
                    key_prefix=raw[:12],
                    key_hash=sha256(raw.encode("utf-8")).hexdigest(),
                    scopes=["events:write"],
                    created_by_user_id=auth.user_id,
                )
            )
            session.add(
                AuditLog(
                    organization_id=auth.organization_id,
                    workspace_id=auth.workspace_id,
                    actor_user_id=auth.user_id,
                    actor_type=auth.via,
                    actor=auth.actor_label,
                    action="api_key_created",
                    resource_type="workspace_api_key",
                    detail={"name": name},
                )
            )
        return raw

    async def list_ingest_keys(self, auth: AuthContext) -> list[dict]:
        if "admin" not in auth.roles:
            raise ForbiddenError("Only workspace admins can list ingest keys.")
        async with session_scope(self.sessions) as session:
            rows = (
                await session.scalars(
                    select(WorkspaceApiKey)
                    .where(WorkspaceApiKey.workspace_id == auth.workspace_id)
                    .order_by(WorkspaceApiKey.created_at.desc())
                )
            ).all()
            return [
                {
                    "id": row.id,
                    "name": row.name,
                    "prefix": row.key_prefix,
                    "scopes": list(row.scopes or []),
                    "created_at": row.created_at,
                    "last_used_at": row.last_used_at,
                    "revoked_at": row.revoked_at,
                }
                for row in rows
            ]

    async def revoke_ingest_key(self, auth: AuthContext, key_id: UUID) -> None:
        if auth.is_demo_workspace:
            raise ForbiddenError("Demo sessions cannot revoke ingest keys.")
        if "admin" not in auth.roles:
            raise ForbiddenError("Only workspace admins can revoke ingest keys.")
        async with session_scope(self.sessions) as session:
            row = await session.get(WorkspaceApiKey, key_id)
            if row is None or row.workspace_id != auth.workspace_id:
                raise NotFoundError("API key not found.")
            if row.revoked_at is None:
                row.revoked_at = utcnow()
                session.add(
                    AuditLog(
                        organization_id=auth.organization_id,
                        workspace_id=auth.workspace_id,
                        actor_user_id=auth.user_id,
                        actor_type=auth.via,
                        actor=auth.actor_label,
                        action="api_key_revoked",
                        resource_type="workspace_api_key",
                        resource_id=row.id,
                    )
                )

    async def _issue(
        self,
        session: AsyncSession,
        user: User,
        organization_id: UUID,
        workspace_id: UUID,
        roles: list[str],
        user_agent: str | None,
    ) -> TokenPair:
        access = encode_access_token(
            secret=self.settings.jwt_secret,
            user_id=user.id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            roles=roles,
            ttl_minutes=self.settings.access_token_minutes,
        )
        refresh = new_refresh_token()
        session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_refresh_token(refresh),
                expires_at=utcnow() + timedelta(days=self.settings.refresh_token_days),
                user_agent=(user_agent or "")[:200] or None,
            )
        )
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            token_type="bearer",
            expires_in=self.settings.access_token_minutes * 60,
            user_id=user.id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            roles=roles,
        )


def slugify(value: str) -> str:
    slug = _SLUG.sub("-", value.lower()).strip("-")
    return (slug or "workspace")[:80]


def _validate_password(password: str) -> None:
    if len(password) < 12:
        raise OpsPilotError("Password must be at least 12 characters.")


async def _unique_slug(session: AsyncSession, model: type[Organization], base: str) -> str:
    candidate = base
    suffix = 1
    while await session.scalar(select(model.id).where(model.slug == candidate)):
        suffix += 1
        candidate = f"{base[:70]}-{suffix}"
    return candidate
