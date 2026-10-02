"""Read models for the console. Writes stay in the workflow and event service."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import NotFoundError
from app.db import session_scope
from app.models import (
    AgentRun,
    AgentStep,
    ApprovalRequest,
    AuditLog,
    Incident,
    IncidentAction,
    IncidentEvidence,
    IncidentHypothesis,
    IncidentTimeline,
    KnowledgeDocument,
    RcaReport,
    ToolCall,
)
from app.rag.retriever import search_similar
from app.schemas.api import (
    ActionOut,
    ApprovalOut,
    DashboardOut,
    EvidenceItemOut,
    EvidenceOut,
    HypothesisOut,
    IncidentDetail,
    IncidentList,
    IncidentSummary,
    KnowledgeOut,
    RcaOut,
    RunOut,
    SearchHit,
    StepOut,
    TimelineOut,
    ToolSummary,
)


class QueryService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def list_incidents(
        self, *, workspace_id: UUID, status: str | None, limit: int, offset: int
    ) -> IncidentList:
        async with session_scope(self.sessions) as session:
            filters = [Incident.workspace_id == workspace_id]
            if status:
                filters.append(Incident.status == status)
            total = await session.scalar(select(func.count()).select_from(Incident).where(*filters))
            rows = (
                await session.scalars(
                    select(Incident)
                    .where(*filters)
                    .order_by(Incident.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return IncidentList(
                items=[_summary(row) for row in rows],
                total=int(total or 0),
            )

    async def get_incident(self, incident_id: UUID, workspace_id: UUID) -> IncidentDetail:
        async with session_scope(self.sessions) as session:
            incident = await self._load_incident(session, incident_id, workspace_id)
            return await self._detail(session, incident)

    async def timeline(self, incident_id: UUID, workspace_id: UUID) -> list[TimelineOut]:
        detail = await self.get_incident(incident_id, workspace_id)
        return detail.timeline

    async def agent_runs(self, incident_id: UUID, workspace_id: UUID) -> list[RunOut]:
        detail = await self.get_incident(incident_id, workspace_id)
        return detail.agent_runs

    async def rca(self, incident_id: UUID, workspace_id: UUID) -> RcaOut:
        detail = await self.get_incident(incident_id, workspace_id)
        if detail.rca is None:
            raise NotFoundError("RCA is not ready.")
        return detail.rca

    async def rca_html(self, incident_id: UUID, workspace_id: UUID) -> tuple[str, str]:
        async with session_scope(self.sessions) as session:
            incident = await self._load_incident(session, incident_id, workspace_id)
            report = await session.scalar(
                select(RcaReport)
                .where(RcaReport.incident_id == incident_id)
                .order_by(RcaReport.version.desc())
            )
            if report is None:
                raise NotFoundError("RCA is not ready.")
            return incident.incident_number, report.html

    async def approval_in_workspace(self, approval_id: UUID, workspace_id: UUID) -> None:
        async with session_scope(self.sessions) as session:
            row = await session.execute(
                select(ApprovalRequest)
                .join(Incident, Incident.id == ApprovalRequest.incident_id)
                .where(ApprovalRequest.id == approval_id, Incident.workspace_id == workspace_id)
            )
            if row.first() is None:
                raise NotFoundError("Approval not found.")

    async def list_approvals(self, status: str | None, workspace_id: UUID) -> list[ApprovalOut]:
        async with session_scope(self.sessions) as session:
            risk_rank = case(
                (ApprovalRequest.risk_level == "HIGH", 0),
                (ApprovalRequest.risk_level == "MEDIUM", 1),
                else_=2,
            )
            stmt = (
                select(ApprovalRequest, Incident)
                .join(Incident, Incident.id == ApprovalRequest.incident_id)
                .where(Incident.workspace_id == workspace_id)
                .order_by(risk_rank, ApprovalRequest.created_at.desc())
            )
            if status in {"PENDING", "PENDING_APPROVAL"}:
                stmt = stmt.where(ApprovalRequest.status == "PENDING_APPROVAL")
            elif status:
                stmt = stmt.where(ApprovalRequest.status == status)
            rows = (await session.execute(stmt)).all()
            return [_approval(request, incident) for request, incident in rows]

    async def list_agent_runs(self, workspace_id: UUID) -> list[RunOut]:
        async with session_scope(self.sessions) as session:
            runs = (
                await session.scalars(
                    select(AgentRun)
                    .join(Incident, Incident.id == AgentRun.incident_id)
                    .where(Incident.workspace_id == workspace_id)
                    .order_by(AgentRun.started_at.desc())
                    .limit(40)
                )
            ).all()
            if not runs:
                return []
            run_ids = [row.id for row in runs]
            steps = (
                await session.scalars(
                    select(AgentStep)
                    .where(AgentStep.run_id.in_(run_ids))
                    .order_by(AgentStep.sequence)
                )
            ).all()
            tools = (
                await session.scalars(
                    select(ToolCall)
                    .where(ToolCall.run_id.in_(run_ids))
                    .order_by(ToolCall.created_at)
                )
            ).all()
            return _runs(runs, steps, tools)

    async def list_audit(self, workspace_id: UUID) -> list[dict]:
        async with session_scope(self.sessions) as session:
            rows = (
                await session.scalars(
                    select(AuditLog)
                    .where(AuditLog.workspace_id == workspace_id)
                    .order_by(AuditLog.created_at.desc())
                    .limit(100)
                )
            ).all()
            return [
                {
                    "id": str(row.id),
                    "actor": row.actor,
                    "action": row.action,
                    "resource_type": row.resource_type,
                    "resource_id": str(row.resource_id) if row.resource_id else None,
                    "detail": row.detail,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]

    async def dashboard(self, workspace_id: UUID) -> DashboardOut:
        async with session_scope(self.sessions) as session:
            scoped = Incident.workspace_id == workspace_id
            active = await session.scalar(
                select(func.count())
                .select_from(Incident)
                .where(
                    scoped,
                    Incident.status != "resolved",
                    Incident.status != "closed",
                )
            )
            investigations = await session.scalar(
                select(func.count())
                .select_from(AgentRun)
                .join(Incident, Incident.id == AgentRun.incident_id)
                .where(scoped)
            )
            pending = await session.scalar(
                select(func.count())
                .select_from(ApprovalRequest)
                .join(Incident, Incident.id == ApprovalRequest.incident_id)
                .where(scoped, ApprovalRequest.status == "PENDING_APPROVAL")
            )
            durations = (
                await session.execute(
                    select(Incident.started_at, Incident.resolved_at).where(
                        scoped, Incident.resolved_at.is_not(None)
                    )
                )
            ).all()
            mttr = None
            if durations:
                seconds = [
                    (resolved - started).total_seconds()
                    for started, resolved in durations
                    if resolved is not None
                ]
                mttr = sum(seconds) / len(seconds) if seconds else None
            terminal = (
                await session.execute(
                    select(IncidentAction.status, func.count())
                    .join(Incident, Incident.id == IncidentAction.incident_id)
                    .where(
                        scoped,
                        IncidentAction.status.in_(("EXECUTED", "FAILED", "REJECTED")),
                    )
                    .group_by(IncidentAction.status)
                )
            ).all()
            counts = {status: count for status, count in terminal}
            denominator = sum(counts.values())
            rate = (counts.get("EXECUTED", 0) / denominator) if denominator else None
            recent = (
                await session.scalars(
                    select(Incident)
                    .where(scoped)
                    .order_by(Incident.created_at.desc())
                    .limit(8)
                )
            ).all()
            activity_rows = (
                await session.execute(
                    select(IncidentTimeline, Incident.incident_number)
                    .join(Incident, Incident.id == IncidentTimeline.incident_id)
                    .where(scoped)
                    .order_by(IncidentTimeline.occurred_at.desc())
                    .limit(12)
                )
            ).all()
            return DashboardOut(
                active_incidents=int(active or 0),
                mttr_seconds=mttr,
                ai_investigations=int(investigations or 0),
                pending_approvals=int(pending or 0),
                automation_success_rate=rate,
                recent_incidents=[_summary(row) for row in recent],
                activity=[_timeline(row, number) for row, number in activity_rows],
            )

    async def knowledge(self, workspace_id: UUID) -> list[KnowledgeOut]:
        async with session_scope(self.sessions) as session:
            rows = (
                await session.scalars(
                    select(KnowledgeDocument)
                    .where(KnowledgeDocument.workspace_id == workspace_id)
                    .order_by(KnowledgeDocument.external_id)
                )
            ).all()
            return [_knowledge(row) for row in rows]

    async def search_knowledge(
        self, query: str, limit: int, workspace_id: UUID
    ) -> list[SearchHit]:
        async with session_scope(self.sessions) as session:
            rows = await search_similar(session, query, limit, workspace_id)
            return [
                SearchHit(
                    external_id=row["external_id"],
                    title=row["title"],
                    service=row["service"],
                    symptoms=row["symptoms"],
                    root_cause=row["root_cause"],
                    resolution=row["resolution"],
                    similarity=float(row["similarity"]),
                )
                for row in rows
            ]

    async def _load_incident(
        self, session: AsyncSession, incident_id: UUID, workspace_id: UUID
    ) -> Incident:
        incident = await session.get(Incident, incident_id)
        if incident is None or incident.workspace_id != workspace_id:
            raise NotFoundError("Incident not found.")
        return incident

    async def _detail(self, session: AsyncSession, incident: Incident) -> IncidentDetail:
        hypotheses = (
            await session.scalars(
                select(IncidentHypothesis)
                .where(IncidentHypothesis.incident_id == incident.id)
                .order_by(IncidentHypothesis.rank)
            )
        ).all()
        actions = (
            await session.scalars(
                select(IncidentAction)
                .where(IncidentAction.incident_id == incident.id)
                .order_by(IncidentAction.created_at)
            )
        ).all()
        approvals = (
            await session.scalars(
                select(ApprovalRequest)
                .where(ApprovalRequest.incident_id == incident.id)
                .order_by(ApprovalRequest.created_at)
            )
        ).all()
        timeline = (
            await session.scalars(
                select(IncidentTimeline)
                .where(IncidentTimeline.incident_id == incident.id)
                .order_by(IncidentTimeline.occurred_at)
            )
        ).all()
        runs = (
            await session.scalars(
                select(AgentRun)
                .where(AgentRun.incident_id == incident.id)
                .order_by(AgentRun.started_at)
            )
        ).all()
        steps = (
            await session.scalars(
                select(AgentStep)
                .where(AgentStep.incident_id == incident.id)
                .order_by(AgentStep.sequence)
            )
        ).all()
        tools = (
            await session.scalars(
                select(ToolCall)
                .where(ToolCall.incident_id == incident.id)
                .order_by(ToolCall.created_at)
            )
        ).all()
        evidence_rows = (
            await session.scalars(
                select(IncidentEvidence)
                .where(IncidentEvidence.incident_id == incident.id)
                .order_by(IncidentEvidence.created_at)
            )
        ).all()
        report = await session.scalar(
            select(RcaReport)
            .where(RcaReport.incident_id == incident.id)
            .order_by(RcaReport.version.desc())
        )
        return IncidentDetail(
            **_summary(incident).model_dump(),
            event_type=incident.event_type,
            scenario_key=incident.scenario_key,
            summary=incident.summary,
            message=incident.message,
            model_used=incident.model_used,
            input_tokens=incident.input_tokens,
            output_tokens=incident.output_tokens,
            execution_time_ms=incident.execution_time_ms,
            last_error=incident.last_error,
            hypotheses=[
                HypothesisOut(
                    id=item.id,
                    key=item.hypothesis_key,
                    title=item.title,
                    description=item.description,
                    confidence=item.confidence,
                    is_primary=item.is_primary,
                    evidence=list(item.evidence or []),
                    evidence_ids=[str(value) for value in (item.evidence_ids or [])],
                    rank=item.rank,
                )
                for item in hypotheses
            ],
            actions=[
                ActionOut(
                    id=item.id,
                    tool_name=item.tool_name,
                    risk_level=item.risk_level,
                    status=item.status,
                    title=item.title,
                    reason=item.reason,
                    expected_impact=item.expected_impact,
                    confidence=item.confidence,
                    arguments=dict(item.arguments or {}),
                    result=dict(item.result) if item.result else None,
                    execution_id=item.execution_id,
                    provider_ref=item.provider_ref,
                    executed_at=item.executed_at,
                    attempt_count=item.attempt_count,
                )
                for item in actions
            ],
            approvals=[_approval(item, incident) for item in approvals],
            timeline=[_timeline(item, incident.incident_number) for item in timeline],
            evidence=_evidence(tools, evidence_rows),
            agent_runs=_runs(runs, steps, tools),
            rca=None
            if report is None
            else RcaOut(
                executive_summary=report.executive_summary,
                impact=report.impact,
                detection=report.detection,
                timeline_narrative=report.timeline_narrative,
                root_cause=report.root_cause,
                contributing_factors=list(report.contributing_factors),
                resolution=report.resolution,
                corrective_actions=list(report.corrective_actions),
                preventive_actions=list(report.preventive_actions),
                confidence=report.confidence,
                evidence_sources=list(report.evidence_sources),
                disclosure=report.disclosure,
                version=report.version,
                created_at=report.created_at,
            ),
        )


def _summary(incident: Incident) -> IncidentSummary:
    return IncidentSummary(
        id=incident.id,
        incident_number=incident.incident_number,
        service=incident.service,
        environment=incident.environment,
        severity=incident.severity,
        status=incident.status,
        title=incident.title,
        error_rate=incident.error_rate,
        current_activity=incident.current_activity,
        started_at=incident.started_at,
        resolved_at=incident.resolved_at,
    )


def _timeline(row: IncidentTimeline, number: str | None) -> TimelineOut:
    return TimelineOut(
        id=row.id,
        incident_id=row.incident_id,
        incident_number=number,
        occurred_at=row.occurred_at,
        event_type=row.event_type,
        title=row.title,
        detail=row.detail,
        actor=row.actor,
    )


def _approval(request: ApprovalRequest, incident: Incident) -> ApprovalOut:
    return ApprovalOut(
        id=request.id,
        incident_id=request.incident_id,
        incident_number=incident.incident_number,
        service=incident.service,
        action_id=request.action_id,
        status=request.status,
        tool_name=request.tool_name,
        title=request.title,
        reason=request.reason,
        risk_level=request.risk_level,
        expected_impact=request.expected_impact,
        confidence=request.confidence,
        evidence=list(request.evidence or []),
        proposed_arguments=dict(request.proposed_arguments or {}),
        created_at=request.created_at,
        decided_by=request.decided_by,
        decided_at=request.decided_at,
    )


def _knowledge(row: KnowledgeDocument) -> KnowledgeOut:
    return KnowledgeOut(
        id=row.id,
        external_id=row.external_id,
        title=row.title,
        service=row.service,
        symptoms=row.symptoms,
        root_cause=row.root_cause,
        resolution=row.resolution,
        created_at=row.created_at,
    )


def _evidence(tools: Sequence[ToolCall], items: Sequence[IncidentEvidence] | None = None) -> EvidenceOut:
    def latest(name: str) -> dict:
        for call in reversed(tools):
            if call.tool_name == name and call.status == "EXECUTED":
                return call.result or {}
        return {}

    return EvidenceOut(
        items=[
            EvidenceItemOut(
                id=row.id,
                source_type=row.source_type,
                source_reference=row.source_reference,
                title=row.title,
                summary=row.summary,
                observed_at=row.observed_at,
                created_at=row.created_at,
            )
            for row in items or []
        ],
        logs=list(latest("search_logs").get("entries", [])),
        deployments=list(latest("get_recent_deployments").get("deployments", [])),
        commits=list(latest("get_recent_commits").get("commits", [])),
        related_incidents=list(latest("search_previous_incidents").get("incidents", [])),
        customer_reports=list(latest("search_customer_reports").get("reports", [])),
    )


def _runs(
    runs: Sequence[AgentRun], steps: Sequence[AgentStep], tools: Sequence[ToolCall]
) -> list[RunOut]:
    output: list[RunOut] = []
    for run in runs:
        run_steps = []
        for step in steps:
            if step.run_id != run.id:
                continue
            step_tools = [
                ToolSummary(
                    id=call.id,
                    tool_name=call.tool_name,
                    risk_level=call.risk_level,
                    status=call.status,
                    result_summary=call.result_summary,
                    latency_ms=call.latency_ms,
                )
                for call in tools
                if call.step_id == step.id
            ]
            run_steps.append(
                StepOut(
                    id=step.id,
                    node_name=step.node_name,
                    sequence=step.sequence,
                    status=step.status,
                    summary=step.summary,
                    evidence=list(step.evidence) if step.evidence else None,
                    confidence=step.confidence,
                    input_tokens=step.input_tokens,
                    output_tokens=step.output_tokens,
                    latency_ms=step.latency_ms,
                    error=step.error,
                    tools=step_tools,
                )
            )
        output.append(
            RunOut(
                id=run.id,
                incident_id=run.incident_id,
                graph_name=run.graph_name,
                status=run.status,
                model=run.model,
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
                latency_ms=run.latency_ms,
                error=run.error,
                started_at=run.started_at,
                finished_at=run.finished_at,
                steps=run_steps,
            )
        )
    return output
