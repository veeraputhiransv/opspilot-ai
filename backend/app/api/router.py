"""HTTP routes. They validate, delegate, and map errors."""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.api.deps import (
    get_context,
    get_ingest_auth,
    limit_approval,
    limit_ingest,
    limit_ticket,
    limit_writes,
    require_admin,
    require_operator,
    require_viewer,
)
from app.identity.context import AuthContext
from app.integrations.demo_data import scenario_catalog
from app.policies.risk_policy import RiskPolicyService
from app.runtime import AppContext
from app.schemas.api import (
    ApprovalOut,
    DashboardOut,
    DecisionIn,
    EventIn,
    HealthOut,
    IncidentCreated,
    IncidentDetail,
    IncidentList,
    KnowledgeOut,
    ModifyIn,
    PolicyRow,
    RcaOut,
    RunOut,
    SearchHit,
    SearchIn,
    SettingsOut,
    TimelineOut,
)

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthOut)
async def health(context: AppContext = Depends(get_context)) -> HealthOut:
    database = "ok"
    try:
        async with context.sessions() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        database = "unavailable"
    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        database=database,
        mode=context.settings.mode,
    )


@router.post("/events", response_model=IncidentCreated, status_code=202)
async def ingest_event(
    body: EventIn,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(get_ingest_auth),
    _: None = Depends(limit_ingest),
) -> JSONResponse:
    created = await context.events.ingest(body, auth)
    status = 200 if created.replayed else 202
    return JSONResponse(status_code=status, content=json.loads(created.model_dump_json()))


@router.get("/demo/scenarios")
async def demo_scenarios(
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_operator),
) -> list[dict]:
    from app.seed.demo import require_demo_seed

    require_demo_seed(context.settings)
    if not auth.is_demo_workspace:
        from app.core.errors import ForbiddenError

        raise ForbiddenError("Incident scenarios are only available in the AcmeFlow demo workspace.")
    return scenario_catalog()


@router.post("/demo/scenarios/{key}/trigger", response_model=IncidentCreated, status_code=202)
async def trigger_demo_scenario(
    key: str,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_operator),
    _: None = Depends(limit_ingest),
) -> JSONResponse:
    from app.core.errors import ForbiddenError, OpsPilotError
    from app.seed.demo import require_demo_seed

    require_demo_seed(context.settings)
    if not auth.is_demo_workspace:
        raise ForbiddenError("Incident scenarios are only available in the AcmeFlow demo workspace.")
    match = next((item for item in scenario_catalog() if item["key"] == key), None)
    if match is None:
        raise OpsPilotError("Unknown demo scenario.")
    created = await context.events.ingest(EventIn.model_validate(match["event"]), auth)
    status = 200 if created.replayed else 202
    return JSONResponse(status_code=status, content=json.loads(created.model_dump_json()))


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
) -> DashboardOut:
    return await context.queries.dashboard(auth.workspace_id)


@router.get("/incidents", response_model=IncidentList)
async def list_incidents(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
) -> IncidentList:
    return await context.queries.list_incidents(
        workspace_id=auth.workspace_id, status=status, limit=limit, offset=offset
    )


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def get_incident(
    incident_id: UUID,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
) -> IncidentDetail:
    return await context.queries.get_incident(incident_id, auth.workspace_id)


@router.get("/incidents/{incident_id}/timeline", response_model=list[TimelineOut])
async def get_timeline(
    incident_id: UUID,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
) -> list[TimelineOut]:
    return await context.queries.timeline(incident_id, auth.workspace_id)


@router.get("/incidents/{incident_id}/agent-runs", response_model=list[RunOut])
async def get_runs(
    incident_id: UUID,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
) -> list[RunOut]:
    return await context.queries.agent_runs(incident_id, auth.workspace_id)


@router.post("/incidents/{incident_id}/resolve", response_model=IncidentDetail)
async def resolve_incident(
    incident_id: UUID,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_operator),
    _: None = Depends(limit_writes),
) -> IncidentDetail:
    await context.queries.get_incident(incident_id, auth.workspace_id)
    await context.workflow.resolve_manual(incident_id, auth.actor_label)
    return await context.queries.get_incident(incident_id, auth.workspace_id)


@router.get("/incidents/{incident_id}/rca", response_model=RcaOut)
async def get_rca(
    incident_id: UUID,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
) -> RcaOut:
    return await context.queries.rca(incident_id, auth.workspace_id)


@router.get("/incidents/{incident_id}/rca/export", response_class=HTMLResponse)
async def export_rca(
    incident_id: UUID,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
) -> HTMLResponse:
    number, html = await context.queries.rca_html(incident_id, auth.workspace_id)
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f'attachment; filename="{number}-rca.html"'},
    )


@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    status: str | None = "PENDING_APPROVAL",
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
) -> list[ApprovalOut]:
    return await context.queries.list_approvals(status, auth.workspace_id)


@router.post("/approvals/{approval_id}/approve", response_model=IncidentDetail)
async def approve(
    approval_id: UUID,
    body: DecisionIn,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_operator),
    _: None = Depends(limit_approval),
) -> IncidentDetail:
    await context.queries.approval_in_workspace(approval_id, auth.workspace_id)
    incident_id = await context.workflow.decide(
        approval_id,
        actor=auth.actor_label,
        decision="APPROVED",
        comment=body.comment,
        arguments=body.arguments,
    )
    return await context.queries.get_incident(incident_id, auth.workspace_id)


@router.post("/approvals/{approval_id}/reject", response_model=IncidentDetail)
async def reject(
    approval_id: UUID,
    body: DecisionIn,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_operator),
    _: None = Depends(limit_approval),
) -> IncidentDetail:
    await context.queries.approval_in_workspace(approval_id, auth.workspace_id)
    incident_id = await context.workflow.decide(
        approval_id, actor=auth.actor_label, decision="REJECTED", comment=body.comment
    )
    return await context.queries.get_incident(incident_id, auth.workspace_id)


@router.post("/approvals/{approval_id}/modify", response_model=IncidentDetail)
async def modify(
    approval_id: UUID,
    body: ModifyIn,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_operator),
    _: None = Depends(limit_approval),
) -> IncidentDetail:
    await context.queries.approval_in_workspace(approval_id, auth.workspace_id)
    incident_id = await context.workflow.decide(
        approval_id,
        actor=auth.actor_label,
        decision="MODIFIED",
        comment=body.comment,
        arguments=body.arguments,
    )
    return await context.queries.get_incident(incident_id, auth.workspace_id)


@router.get("/agent-runs", response_model=list[RunOut])
async def list_agent_runs(
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
) -> list[RunOut]:
    return await context.queries.list_agent_runs(auth.workspace_id)


@router.get("/integrations")
async def list_integrations(
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
) -> dict:
    connections = await context.integrations.list_connections(auth)
    return {
        "connections": connections,
        "note": "Credentials are never returned. Adapters are replaceable behind integration protocols.",
    }


class IntegrationConnectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    display_name: str = Field(min_length=2, max_length=120)
    secrets: dict
    configuration: dict = Field(default_factory=dict)


@router.post("/integrations/{provider}/connect")
async def connect_integration(
    provider: str,
    body: IntegrationConnectIn,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_admin),
    _: None = Depends(limit_writes),
) -> dict:
    return await context.integrations.connect(
        auth, provider, body.display_name, body.secrets, body.configuration
    )


@router.post("/integrations/{provider}/verify")
async def verify_integration(
    provider: str,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_operator),
    _: None = Depends(limit_writes),
) -> dict:
    return await context.integrations.verify(auth, provider)


@router.post("/integrations/{provider}/disconnect")
async def disconnect_integration(
    provider: str,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_admin),
    _: None = Depends(limit_writes),
) -> dict:
    return await context.integrations.disconnect(auth, provider)


@router.get("/audit")
async def list_audit(
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_admin),
) -> list[dict]:
    return await context.queries.list_audit(auth.workspace_id)


class TicketIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: UUID | None = None


@router.post("/realtime/tickets")
async def create_stream_ticket(
    body: TicketIn,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
    _: None = Depends(limit_ticket),
) -> dict:
    if body.incident_id is not None:
        await context.queries.get_incident(body.incident_id, auth.workspace_id)
    return await context.tickets.issue(auth, body.incident_id)


@router.get("/knowledge", response_model=list[KnowledgeOut])
async def knowledge(
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
) -> list[KnowledgeOut]:
    return await context.queries.knowledge(auth.workspace_id)


@router.post("/knowledge/search", response_model=list[SearchHit])
async def search_knowledge(
    body: SearchIn,
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
) -> list[SearchHit]:
    return await context.queries.search_knowledge(body.query, body.limit, auth.workspace_id)


@router.get("/settings", response_model=SettingsOut)
async def settings_view(
    context: AppContext = Depends(get_context),
    auth: AuthContext = Depends(require_viewer),
) -> SettingsOut:
    del auth
    settings = context.settings
    policy = RiskPolicyService(settings)
    return SettingsOut(
        mode=settings.mode,
        reasoning_model=settings.reasoning_model,
        llm_enabled=bool(settings.llm_enabled and settings.openai_api_key),
        step_delay_ms=settings.step_delay_ms,
        policies=[PolicyRow.model_validate(row) for row in policy.catalog()],
        integrations={
            "github": bool(settings.github_token),
            "slack": bool(settings.slack_webhook_url),
            "rollback_webhook": bool(settings.rollback_webhook),
            "restart_webhook": bool(settings.restart_webhook),
            "logs": bool(settings.log_query_url),
            "smtp": bool(settings.smtp_host and settings.smtp_from),
        },
    )


@router.get("/events/stream")
async def stream(
    ticket: str,
    incident_id: UUID | None = None,
    context: AppContext = Depends(get_context),
) -> StreamingResponse:
    record = await context.tickets.consume(ticket, incident_id=incident_id)
    workspace_id = record["workspace_id"]
    scoped = record.get("incident_id") or (str(incident_id) if incident_id else None)
    if incident_id is not None:
        await context.queries.get_incident(incident_id, UUID(workspace_id))
    queue, unsubscribe = context.bus.subscribe(workspace_id, scoped)

    async def generate():
        try:
            yield "event: ready\ndata: {}\n\n"
            while True:
                try:
                    item = await _wait(queue)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            unsubscribe()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _wait(queue):
    import asyncio

    return await asyncio.wait_for(queue.get(), timeout=15)
