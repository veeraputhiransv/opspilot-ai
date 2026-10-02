"""Workspace integration lifecycle. Credentials stay in the vault."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import ForbiddenError, NotFoundError, OpsPilotError
from app.core.redaction import redact
from app.db import session_scope
from app.identity.context import AuthContext
from app.integrations.catalog import CAPABILITIES, PROVIDERS, provider_for_capability
from app.integrations.deployments import DeploymentAdapter
from app.integrations.email import EmailAdapter
from app.integrations.github import GitHubAdapter
from app.integrations.logs import LogsAdapter
from app.integrations.slack import SlackAdapter
from app.models.identity import IntegrationConnection
from app.services.audit import audit_row
from app.services.vault import SecretVaultService, VaultError
from app.tools.base import ToolResult


class IntegrationService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        vault: SecretVaultService,
    ) -> None:
        self.sessions = sessions
        self.settings = settings
        self.vault = vault

    async def list_connections(self, auth: AuthContext) -> list[dict]:
        async with session_scope(self.sessions) as session:
            rows = (
                await session.scalars(
                    select(IntegrationConnection)
                    .where(IntegrationConnection.workspace_id == auth.workspace_id)
                    .order_by(IntegrationConnection.provider)
                )
            ).all()
            existing = {row.provider: row for row in rows}
            output = []
            for provider in PROVIDERS:
                row = existing.get(provider)
                output.append(_public(provider, row))
            return output

    async def connect(
        self,
        auth: AuthContext,
        provider: str,
        display_name: str,
        secrets: dict,
        configuration: dict,
    ) -> dict:
        if auth.is_demo_workspace:
            raise ForbiddenError("Demo sessions cannot connect real integrations.")
        if "admin" not in auth.roles:
            raise ForbiddenError("Only workspace admins can connect integrations.")
        if provider not in PROVIDERS:
            raise OpsPilotError("Unknown integration provider.")
        sealed = self.vault.encrypt(secrets)
        async with session_scope(self.sessions) as session:
            row = await session.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.workspace_id == auth.workspace_id,
                    IntegrationConnection.provider == provider,
                )
            )
            if row is None:
                row = IntegrationConnection(
                    workspace_id=auth.workspace_id,
                    provider=provider,
                    display_name=display_name[:120],
                    status="CONFIGURED",
                    encrypted_credentials=sealed,
                    configuration=configuration,
                    created_by=auth.user_id,
                )
                session.add(row)
            else:
                row.display_name = display_name[:120]
                row.encrypted_credentials = sealed
                row.configuration = configuration
                row.status = "CONFIGURED"
                row.last_error = None
            session.add(
                audit_row(
                    auth=auth,
                    action="integration_connect",
                    resource_type="integration_connection",
                    resource_id=row.id,
                    detail={"provider": provider},
                )
            )
            await session.flush()
            return _public(provider, row)

    async def verify(self, auth: AuthContext, provider: str) -> dict:
        if "admin" not in auth.roles and "operator" not in auth.roles:
            raise ForbiddenError("You cannot verify this integration.")
        async with session_scope(self.sessions) as session:
            row = await self._load(session, auth.workspace_id, provider)
            row.status = "VERIFYING"
            if bool((row.configuration or {}).get("simulation")):
                from app.models.base import utcnow

                row.status = "CONNECTED"
                row.last_verified_at = utcnow()
                row.last_error = None
                session.add(
                    audit_row(
                        auth=auth,
                        action="integration_verify",
                        resource_type="integration_connection",
                        resource_id=row.id,
                        detail={"provider": provider, "status": row.status, "simulation": True},
                    )
                )
                return _public(provider, row)
            secrets = self._secrets(row)
            try:
                await self._adapter(provider, secrets, row.configuration).verify()  # type: ignore[union-attr]
                row.status = "CONNECTED"
                from app.models.base import utcnow

                row.last_verified_at = utcnow()
                row.last_error = None
            except Exception as exc:
                row.status = "ERROR"
                row.last_error = redact(str(exc))[:400]
            session.add(
                audit_row(
                    auth=auth,
                    action="integration_verify",
                    resource_type="integration_connection",
                    resource_id=row.id,
                    detail={"provider": provider, "status": row.status},
                )
            )
            return _public(provider, row)

    async def disconnect(self, auth: AuthContext, provider: str) -> dict:
        if auth.is_demo_workspace:
            raise ForbiddenError("Demo sessions cannot change integration configuration.")
        if "admin" not in auth.roles:
            raise ForbiddenError("Only workspace admins can disconnect integrations.")
        async with session_scope(self.sessions) as session:
            row = await self._load(session, auth.workspace_id, provider)
            row.encrypted_credentials = None
            row.status = "DISABLED"
            row.last_error = None
            session.add(
                audit_row(
                    auth=auth,
                    action="integration_disconnect",
                    resource_type="integration_connection",
                    resource_id=row.id,
                    detail={"provider": provider},
                )
            )
            return _public(provider, row)

    async def credentials(self, workspace_id: UUID, provider: str) -> dict:
        async with session_scope(self.sessions) as session:
            row = await session.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.workspace_id == workspace_id,
                    IntegrationConnection.provider == provider,
                )
            )
            if row is None or not row.encrypted_credentials:
                return {}
            if row.workspace_id != workspace_id:
                raise NotFoundError("Integration not found.")
            return self._secrets(row)

    async def run_capability(
        self,
        workspace_id: UUID,
        capability: str,
        payload: dict,
        *,
        idempotency_key: str = "",
    ) -> ToolResult:
        provider = provider_for_capability(capability)
        if provider is None:
            return ToolResult("FAILED", f"Unknown capability {capability}.", {})
        async with session_scope(self.sessions) as session:
            row = await session.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.workspace_id == workspace_id,
                    IntegrationConnection.provider == provider,
                )
            )
            secrets = self._secrets(row) if row else {}
            configuration = dict(row.configuration or {}) if row else {}
            if row is not None and row.status == "DISABLED":
                return ToolResult("FAILED", f"{provider} is disabled.", {})
        adapter = self._adapter(provider, secrets, configuration)
        if adapter is None:
            return ToolResult("FAILED", f"{provider} is not configured.", {})
        try:
            if capability == "source.recent_commits":
                repo = _resolve_repo(configuration, str(payload.get("service") or ""), payload.get("repo"))
                return await adapter.recent_commits(repo)
            if capability == "source.pull_requests":
                repo = _resolve_repo(configuration, str(payload.get("service") or ""), payload.get("repo"))
                return await adapter.pull_requests(repo)
            if capability == "action.create_issue":
                return await adapter.create_issue(
                    str(payload["repo"]),
                    str(payload["title"]),
                    str(payload["body"]),
                    idempotency_key or "issue",
                )
            if capability == "communication.send":
                return await adapter.send(
                    str(payload["channel"]), str(payload["text"]), idempotency_key or "slack"
                )
            if capability == "email.send":
                return await adapter.send(
                    str(payload["to_group"]),
                    str(payload["subject"]),
                    str(payload["body"]),
                    idempotency_key or "email",
                )
            if capability == "logs.search":
                from datetime import datetime

                start = payload.get("start_time")
                end = payload.get("end_time")
                return await adapter.search(
                    service=str(payload.get("service") or ""),
                    environment=str(payload.get("environment") or ""),
                    start_time=datetime.fromisoformat(start) if start else None,
                    end_time=datetime.fromisoformat(end) if end else None,
                    severity=payload.get("severity"),
                    search_terms=str(payload.get("search_terms") or ""),
                    limit=int(payload.get("limit") or 50),
                )
            if capability == "deployment.list":
                return await adapter.history(str(payload.get("service") or ""))
            if capability == "deployment.rollback":
                return await adapter.rollback(
                    str(payload["service"]),
                    str(payload["from_version"]),
                    str(payload["to_version"]),
                    dry_run=bool(payload.get("dry_run")),
                    idempotency_key=idempotency_key or "rollback",
                )
            if capability == "service.restart":
                return await adapter.restart(
                    str(payload["service"]),
                    str(payload["environment"]),
                    dry_run=bool(payload.get("dry_run")),
                    idempotency_key=idempotency_key or "restart",
                )
        except ValueError as exc:
            return ToolResult("FAILED", str(exc), {})
        return ToolResult("FAILED", f"Capability {capability} is not implemented.", {})

    def _secrets(self, row: IntegrationConnection) -> dict:
        if not row.encrypted_credentials:
            return {}
        try:
            return self.vault.decrypt(row.encrypted_credentials)
        except VaultError:
            return {}

    async def _load(self, session: AsyncSession, workspace_id: UUID, provider: str) -> IntegrationConnection:
        row = await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.workspace_id == workspace_id,
                IntegrationConnection.provider == provider,
            )
        )
        if row is None:
            raise NotFoundError("Integration not found.")
        return row

    def _adapter(self, provider: str, secrets: dict, configuration: dict):
        if provider == "github":
            repos = set(configuration.get("allowed_repos") or [])
            token = str(secrets.get("token") or "")
            return GitHubAdapter(token, repos)
        if provider == "slack":
            channels = set(configuration.get("allowed_channels") or [])
            return SlackAdapter(str(secrets.get("webhook_url") or ""), channels)
        if provider == "email":
            groups = dict(configuration.get("allowed_groups") or {})
            return EmailAdapter(
                host=str(secrets.get("host") or self.settings.smtp_host),
                port=int(secrets.get("port") or self.settings.smtp_port),
                username=str(secrets.get("username") or self.settings.smtp_username),
                password=str(secrets.get("password") or self.settings.smtp_password),
                mail_from=str(secrets.get("from") or self.settings.smtp_from),
                allowed_groups=groups,
            )
        if provider == "logs":
            return LogsAdapter(str(secrets.get("query_url") or self.settings.log_query_url))
        if provider == "deployments":
            return DeploymentAdapter(
                str(secrets.get("rollback_url") or self.settings.rollback_webhook),
                str(secrets.get("restart_url") or self.settings.restart_webhook),
                set(configuration.get("allowed_services") or []),
            )
        return None


def _public(provider: str, row: IntegrationConnection | None) -> dict:
    return {
        "provider": provider,
        "connected": bool(row and row.status == "CONNECTED"),
        "display_name": row.display_name if row else provider,
        "status": row.status if row else "DISCONNECTED",
        "last_verified_at": row.last_verified_at.isoformat() if row and row.last_verified_at else None,
        "last_error": row.last_error if row else None,
        "capabilities": list(CAPABILITIES.get(provider, ())),
        "has_credentials": bool(row and row.encrypted_credentials),
        "simulation": bool(row and (row.configuration or {}).get("simulation")),
    }


def _resolve_repo(configuration: dict, service: str, requested: object) -> str:
    mapping = dict(configuration.get("service_repos") or {})
    if isinstance(requested, str) and requested:
        return requested
    if service and service in mapping:
        return str(mapping[service])
    allowed = [str(item) for item in (configuration.get("allowed_repos") or [])]
    if len(allowed) == 1:
        return allowed[0]
    raise ValueError("No repository allowlisted for this service.")
