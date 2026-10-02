"""Idempotent AcmeFlow demo seed and reset. Disabled unless explicitly enabled."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ForbiddenError
from app.identity.passwords import hash_password
from app.integrations.catalog import PROVIDERS
from app.models import (
    AgentRun,
    Incident,
    IncidentAction,
    IncidentHypothesis,
    IncidentTimeline,
    KnowledgeDocument,
    RcaReport,
)
from app.models.base import utcnow
from app.models.identity import (
    IntegrationConnection,
    Organization,
    OrganizationMember,
    User,
    UserIdentity,
    Workspace,
    WorkspaceIncidentCounter,
    WorkspaceMember,
)
from app.rag.corpus import CORPUS
from app.rag.embeddings import MODEL_NAME, embed, vector_literal
from app.seed.constants import (
    DEMO_ORG_NAME,
    DEMO_ORG_SLUG,
    DEMO_USER_EMAIL,
    DEMO_USER_NAME,
    DEMO_WORKSPACE_NAME,
    DEMO_WORKSPACE_SLUG,
    HISTORICAL_INCIDENT_NUMBERS,
)
from app.services.rca_document import render_rca_html

_SIMULATED_INTEGRATIONS = (
    ("github", "GitHub", ["acmeflow/payment-service", "acmeflow/checkout-api"]),
    ("slack", "Slack", ["#payments-oncall"]),
    ("email", "Email", ["impacted_customers"]),
    ("logs", "Logs", ["payment-service", "checkout-api"]),
    ("deployments", "Deployment Platform", ["payment-service", "checkout-api"]),
)

_HISTORY: list[dict[str, Any]] = [
    {
        "number": "INC-0087",
        "service": "payment-service",
        "event_type": "error_rate_spike",
        "scenario_key": "db_pool",
        "severity": "SEV-1",
        "title": "Payment Service Connection Pool Exhaustion",
        "message": "Database connection timeout",
        "error_rate": 68,
        "summary": "A configuration refactor reduced the Postgres pool and checkout requests timed out.",
        "hours_ago": 280,
        "minutes": 14,
        "cause": "Database connection pool exhaustion after a pool-size reduction",
        "key": "db_pool",
        "tool": "rollback_deployment",
        "action": "Rollback payment-service from v2.4.2 to v2.4.1",
    },
    {
        "number": "INC-0092",
        "service": "payment-service",
        "event_type": "upstream_latency",
        "scenario_key": "stripe",
        "severity": "SEV-2",
        "title": "Stripe API Latency",
        "message": "Stripe API latency elevated",
        "error_rate": 36,
        "summary": "Checkout timed out on Stripe. The local pool stayed healthy.",
        "hours_ago": 190,
        "minutes": 42,
        "cause": "Third-party Stripe degradation",
        "key": "stripe",
        "tool": "create_github_issue",
        "action": "Open tracking issue for Stripe API latency",
    },
    {
        "number": "INC-0101",
        "service": "redis-session",
        "event_type": "dependency_down",
        "scenario_key": "redis",
        "severity": "SEV-1",
        "title": "Redis Session Outage",
        "message": "Redis connection refused",
        "error_rate": 81,
        "summary": "redis-session exhausted memory and refused new connections.",
        "hours_ago": 140,
        "minutes": 9,
        "cause": "Redis memory exhaustion",
        "key": "redis",
        "tool": "restart_service",
        "action": "Restart redis-session",
    },
    {
        "number": "INC-0114",
        "service": "checkout-api",
        "event_type": "deploy_regression",
        "scenario_key": "bad_deploy",
        "severity": "SEV-1",
        "title": "Bad Checkout Deployment",
        "message": "NullPointerException in charge validation",
        "error_rate": 64,
        "summary": "A null-handling regression shipped in checkout-api and failed valid cards.",
        "hours_ago": 96,
        "minutes": 11,
        "cause": "Null handling regression after deployment",
        "key": "bad_deploy",
        "tool": "rollback_deployment",
        "action": "Rollback checkout-api from v3.2.1 to v3.2.0",
    },
    {
        "number": "INC-0120",
        "service": "notification-worker",
        "event_type": "error_rate_spike",
        "scenario_key": "false_positive",
        "severity": "SEV-4",
        "title": "False Positive CPU Alert",
        "message": "Brief CPU alert recovered during nightly batch",
        "error_rate": 1.1,
        "summary": "A legitimate batch process tripped a CPU detector. No customer impact.",
        "hours_ago": 36,
        "minutes": 3,
        "cause": "Legitimate batch process",
        "key": "false_positive",
        "tool": None,
        "action": None,
    },
    {
        "number": "INC-0066",
        "service": "identity-service",
        "event_type": "auth_failures",
        "scenario_key": "unknown",
        "severity": "SEV-2",
        "title": "Identity token verification failures",
        "message": "JWT validation failed because of clock skew",
        "error_rate": 18,
        "summary": "identity-service rejected tokens after a brief NTP drift.",
        "hours_ago": 400,
        "minutes": 22,
        "cause": "Clock skew on the identity issuer",
        "key": "insufficient",
        "tool": None,
        "action": None,
    },
    {
        "number": "INC-0078",
        "service": "customer-api",
        "event_type": "latency_spike",
        "scenario_key": "unknown",
        "severity": "SEV-3",
        "title": "Customer API read replica lag",
        "message": "customer-api p95 latency elevated on account reads",
        "error_rate": 9,
        "summary": "postgres-primary replica lag delayed customer profile reads in staging first, then production.",
        "hours_ago": 330,
        "minutes": 28,
        "cause": "Read replica lag on postgres-primary",
        "key": "insufficient",
        "tool": None,
        "action": None,
    },
]


def require_demo_seed(settings: Settings) -> None:
    if not settings.demo_seed_enabled:
        raise ForbiddenError("Demo features are disabled. Set OPSPILOT_DEMO_SEED_ENABLED=true.")


async def seed_demo(session: AsyncSession, settings: Settings) -> dict[str, str]:
    require_demo_seed(settings)
    org, workspace, user = await _ensure_identity(session, settings)
    await _ensure_counter(session, workspace.id)
    await _seed_knowledge(session, workspace.id)
    await _seed_history(session, org.id, workspace.id)
    await _seed_integrations(session, workspace.id)
    return {
        "organization_id": str(org.id),
        "workspace_id": str(workspace.id),
        "user_id": str(user.id),
        "email": user.email,
        "role": "operator",
    }


async def reset_demo(session: AsyncSession, settings: Settings) -> dict[str, int]:
    require_demo_seed(settings)
    workspace = await session.scalar(select(Workspace).where(Workspace.slug == DEMO_WORKSPACE_SLUG))
    if workspace is None:
        return {"removed_incidents": 0, "removed_knowledge_documents": 0}
    rows = (
        await session.scalars(
            select(Incident).where(
                Incident.workspace_id == workspace.id,
                Incident.incident_number.notin_(HISTORICAL_INCIDENT_NUMBERS),
            )
        )
    ).all()
    removed = 0
    for incident in rows:
        await session.delete(incident)
        removed += 1
    counter = await session.get(WorkspaceIncidentCounter, workspace.id)
    if counter is not None:
        counter.next_number = 1024
    keep_ids = {document["external_id"] for document in CORPUS} | set(HISTORICAL_INCIDENT_NUMBERS)
    leftover_docs = (
        await session.scalars(
            select(KnowledgeDocument).where(
                KnowledgeDocument.workspace_id == workspace.id,
                KnowledgeDocument.external_id.notin_(keep_ids),
            )
        )
    ).all()
    removed_docs = 0
    for document in leftover_docs:
        await session.delete(document)
        removed_docs += 1
    return {"removed_incidents": removed, "removed_knowledge_documents": removed_docs}


async def demo_workspace_ids(session: AsyncSession) -> tuple[UUID, UUID] | None:
    row = (
        await session.execute(
            select(Organization, Workspace)
            .join(Workspace, Workspace.organization_id == Organization.id)
            .where(Organization.slug == DEMO_ORG_SLUG, Workspace.slug == DEMO_WORKSPACE_SLUG)
        )
    ).first()
    if row is None:
        return None
    org, workspace = row
    return org.id, workspace.id


async def _ensure_identity(
    session: AsyncSession, settings: Settings
) -> tuple[Organization, Workspace, User]:
    org = await session.scalar(select(Organization).where(Organization.slug == DEMO_ORG_SLUG))
    if org is None:
        org = Organization(name=DEMO_ORG_NAME, slug=DEMO_ORG_SLUG, status="active")
        session.add(org)
        await session.flush()
    else:
        org.name = DEMO_ORG_NAME
        org.status = "active"

    workspace = await session.scalar(
        select(Workspace).where(
            Workspace.organization_id == org.id,
            Workspace.slug == DEMO_WORKSPACE_SLUG,
        )
    )
    if workspace is None:
        workspace = Workspace(
            organization_id=org.id,
            name=DEMO_WORKSPACE_NAME,
            slug=DEMO_WORKSPACE_SLUG,
            status="active",
        )
        session.add(workspace)
        await session.flush()
    else:
        workspace.name = DEMO_WORKSPACE_NAME
        workspace.status = "active"

    user = await session.scalar(select(User).where(User.email == DEMO_USER_EMAIL))
    password_hash = hash_password(settings.demo_password)
    if user is None:
        user = User(
            email=DEMO_USER_EMAIL,
            password_hash=password_hash,
            full_name=DEMO_USER_NAME,
            status="active",
        )
        session.add(user)
        await session.flush()
        session.add(
            UserIdentity(
                user_id=user.id,
                provider="password",
                subject=str(user.id),
                email=DEMO_USER_EMAIL,
            )
        )
    else:
        user.full_name = DEMO_USER_NAME
        user.status = "active"
        user.password_hash = password_hash

    org_member = await session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.user_id == user.id,
        )
    )
    if org_member is None:
        session.add(OrganizationMember(organization_id=org.id, user_id=user.id, role="member"))
    else:
        org_member.role = "member"

    ws_member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if ws_member is None:
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="operator"))
    else:
        ws_member.role = "operator"

    return org, workspace, user


async def _ensure_counter(session: AsyncSession, workspace_id: UUID) -> None:
    counter = await session.get(WorkspaceIncidentCounter, workspace_id)
    if counter is None:
        session.add(WorkspaceIncidentCounter(workspace_id=workspace_id, next_number=1024))
    elif counter.next_number < 1024:
        counter.next_number = 1024


async def _seed_knowledge(session: AsyncSession, workspace_id: UUID) -> None:
    for document in CORPUS:
        existing = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.workspace_id == workspace_id,
                KnowledgeDocument.external_id == document["external_id"],
            )
        )
        if existing is not None:
            existing.title = document["title"]
            existing.service = document["service"]
            existing.symptoms = document["symptoms"]
            existing.root_cause = document["root_cause"]
            existing.resolution = document["resolution"]
            existing.timeline_text = document["timeline_text"]
            continue
        row = KnowledgeDocument(
            workspace_id=workspace_id,
            external_id=document["external_id"],
            title=document["title"],
            service=document["service"],
            symptoms=document["symptoms"],
            root_cause=document["root_cause"],
            resolution=document["resolution"],
            timeline_text=document["timeline_text"],
            meta={"source": "demo_corpus"},
        )
        session.add(row)
        await session.flush()
        blob = " ".join(
            [
                document["title"],
                document["service"],
                document["symptoms"],
                document["root_cause"],
                document["resolution"],
            ]
        )
        await session.execute(
            text(
                """
                INSERT INTO incident_embeddings (id, document_id, embedding, model, created_at)
                VALUES (:id, :document_id, CAST(:embedding AS vector), :model, now())
                """
            ),
            {
                "id": uuid4(),
                "document_id": row.id,
                "embedding": vector_literal(embed(blob)),
                "model": MODEL_NAME,
            },
        )


async def _seed_history(session: AsyncSession, organization_id: UUID, workspace_id: UUID) -> None:
    now = utcnow()
    for spec in _HISTORY:
        existing = await session.scalar(
            select(Incident).where(
                Incident.workspace_id == workspace_id,
                Incident.incident_number == spec["number"],
            )
        )
        if existing is not None:
            continue
        started = now - timedelta(hours=int(spec["hours_ago"]))
        resolved = started + timedelta(minutes=int(spec["minutes"]))
        incident = Incident(
            organization_id=organization_id,
            workspace_id=workspace_id,
            incident_number=spec["number"],
            service=spec["service"],
            environment="production",
            event_type=spec["event_type"],
            scenario_key=spec["scenario_key"],
            severity=spec["severity"],
            status="resolved",
            title=spec["title"],
            summary=spec["summary"],
            message=spec["message"],
            error_rate=spec["error_rate"],
            current_activity="Resolved",
            model_used="opspilot-deterministic-v1",
            execution_time_ms=int(spec["minutes"]) * 1000,
            started_at=started,
            resolved_at=resolved,
        )
        session.add(incident)
        await session.flush()
        session.add(
            IncidentHypothesis(
                incident_id=incident.id,
                hypothesis_key=spec["key"],
                title=spec["cause"],
                description=spec["summary"],
                confidence=0.9 if spec["key"] != "false_positive" else 0.93,
                is_primary=True,
                evidence=[spec["summary"]],
                rank=1,
            )
        )
        if spec["tool"]:
            session.add(
                IncidentAction(
                    incident_id=incident.id,
                    tool_name=spec["tool"],
                    risk_level="HIGH" if spec["tool"] != "create_github_issue" else "MEDIUM",
                    status="EXECUTED",
                    title=spec["action"],
                    reason=spec["summary"],
                    expected_impact="Recorded from the historical incident.",
                    confidence=0.9,
                    arguments={"service": spec["service"]},
                    result={"simulated": True, "summary": "Completed during the original incident."},
                )
            )
        session.add(
            AgentRun(
                incident_id=incident.id,
                graph_name="incident_response",
                status="completed",
                model="opspilot-deterministic-v1",
                input_tokens=0,
                output_tokens=0,
                latency_ms=4200,
                started_at=started,
                finished_at=resolved,
            )
        )
        for offset, title in (
            (0, "Alert received"),
            (1, "Root cause hypothesis generated"),
            (2, "Incident resolved"),
        ):
            session.add(
                IncidentTimeline(
                    incident_id=incident.id,
                    occurred_at=started + timedelta(minutes=offset),
                    event_type="history",
                    title=title,
                    detail=spec["summary"],
                    actor="agent",
                )
            )
        report = RcaReport(
            incident_id=incident.id,
            executive_summary=spec["summary"],
            impact=f"{spec['service']} error rate reached {spec['error_rate']}%.",
            detection=f"Detected from {spec['event_type']}.",
            timeline_narrative="Alert, investigation, resolution.",
            root_cause=spec["cause"],
            contributing_factors=[spec["summary"]],
            resolution="See the corrective action recorded on the incident.",
            corrective_actions=[spec["action"] or "No production change."],
            preventive_actions=["Keep this incident in retrieval memory."],
            confidence=0.9,
            evidence_sources=["Historical record"],
            disclosure=(
                "This RCA was authored from a historical record. Severity and actions "
                "were not generated by an unconstrained language model."
            ),
            html="",
        )
        report.html = render_rca_html(incident, report)
        session.add(report)


async def _seed_integrations(session: AsyncSession, workspace_id: UUID) -> None:
    now = utcnow()
    for provider, display_name, allowlist in _SIMULATED_INTEGRATIONS:
        if provider not in PROVIDERS:
            continue
        row = await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.workspace_id == workspace_id,
                IntegrationConnection.provider == provider,
            )
        )
        configuration = {
            "simulation": True,
            "allowed_repos": allowlist if provider == "github" else [],
            "allowed_channels": allowlist if provider == "slack" else [],
            "allowed_services": allowlist if provider == "deployments" else [],
        }
        if row is None:
            session.add(
                IntegrationConnection(
                    workspace_id=workspace_id,
                    provider=provider,
                    display_name=display_name,
                    status="CONNECTED",
                    encrypted_credentials=None,
                    configuration=configuration,
                    last_verified_at=now,
                )
            )
        elif not row.encrypted_credentials:
            row.display_name = display_name
            row.status = "CONNECTED"
            row.configuration = {**(row.configuration or {}), **configuration}
            row.last_verified_at = row.last_verified_at or now
