"""Incident workflow.

The graph is paused by returning. Approval state lives in Postgres. Resume reads
those rows under the same per-incident lock that the investigation holds, so a
click cannot approve a tool while the planner is still writing it.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.llm import maybe_rewrite_summary
from app.agents.reasoner import DeterministicReasoner
from app.agents.state import Evidence, IncidentState
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, PolicyViolation
from app.core.redaction import looks_like_injection, redact
from app.db import session_scope
from app.events.bus import EventBus
from app.graphs.incident_graph import build_investigation_graph, build_resume_graph
from app.models import (
    AgentRun,
    AgentStep,
    ApprovalDecision,
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
    WorkflowCheckpoint,
)
from app.models.base import utcnow
from app.policies.risk_policy import MITIGATING_TOOLS, RiskPolicyService
from app.rag.embeddings import MODEL_NAME, embed, vector_literal
from app.rag.retriever import retrieval_query
from app.services.evidence_store import persist_tool_evidence
from app.services.rca_document import render_rca_html
from app.tools.registry import ToolContext, ToolRegistry, build_registry

logger = logging.getLogger("opspilot.workflow")


class IncidentWorkflow:
    def __init__(
        self,
        settings: Settings,
        sessions: async_sessionmaker[AsyncSession],
        bus: EventBus,
        integrations: Any | None = None,
    ) -> None:
        self.settings = settings
        self.sessions = sessions
        self.bus = bus
        self.integrations = integrations
        self.policy = RiskPolicyService(settings)
        self.reasoner = DeterministicReasoner()
        self.tools: ToolRegistry = build_registry()
        self._locks: dict[str, asyncio.Lock] = {}
        self._investigation: Any = build_investigation_graph(self)
        self._resume_graph: Any = build_resume_graph(self)

    def _lock(self, incident_id: UUID) -> asyncio.Lock:
        return self._locks.setdefault(str(incident_id), asyncio.Lock())

    async def start(self, incident_id: UUID) -> None:
        async with self._lock(incident_id):
            run_id = await self._open_run(incident_id)
            workspace_id = await self._workspace_id(incident_id)
            state: IncidentState = {
                "incident_id": str(incident_id),
                "run_id": str(run_id),
                "workspace_id": str(workspace_id),
                "phase": "investigate",
                "model_used": self.reasoner.name,
                "errors": [],
            }
            try:
                await self._investigation.ainvoke(state)
            except Exception as exc:
                logger.exception("investigation_failed incident=%s", incident_id)
                await self._fail(incident_id, run_id, exc)
                return
            await self._finish_run(incident_id, run_id)

    async def decide(
        self,
        approval_id: UUID,
        *,
        actor: str,
        decision: Literal["APPROVED", "REJECTED", "MODIFIED"],
        comment: str,
        arguments: dict | None = None,
    ) -> UUID:
        async with session_scope(self.sessions) as session:
            request = await session.get(ApprovalRequest, approval_id)
            if request is None:
                raise NotFoundError("Approval request not found.")
            incident_id = request.incident_id

        async with self._lock(incident_id):
            async with session_scope(self.sessions) as session:
                request = await session.get(ApprovalRequest, approval_id, with_for_update=True)
                if request is None:
                    raise NotFoundError("Approval request not found.")
                if request.status != "PENDING_APPROVAL":
                    raise ConflictError("This approval has already been decided.")
                action = await session.get(IncidentAction, request.action_id)
                if action is None:
                    raise NotFoundError("Action not found.")
                incident = await self._require(session, incident_id)
                if decision == "MODIFIED" or (decision == "APPROVED" and arguments):
                    updated = dict(arguments or {})
                    self._validate_action(incident, action.tool_name, updated)
                    self.policy.validate_arguments(
                        action.tool_name,
                        updated,
                        known_versions=await self._known_versions(session, incident.id),
                    )
                    action.arguments = updated
                    request.proposed_arguments = updated
                else:
                    self._validate_action(incident, action.tool_name, dict(action.arguments))
                request.status = "APPROVED" if decision in {"APPROVED", "MODIFIED"} else decision
                action.status = request.status
                request.decided_by = actor
                request.decided_at = utcnow()
                request.decision_reason = comment
                action.updated_at = utcnow()
                request.updated_at = utcnow()
                session.add(
                    ApprovalDecision(
                        approval_request_id=request.id,
                        decision=decision,
                        actor=actor,
                        comment=comment,
                        arguments=arguments if decision == "MODIFIED" else dict(action.arguments),
                    )
                )
                session.add(
                    AuditLog(
                        incident_id=incident_id,
                        actor=actor,
                        action=f"approval_{decision.lower()}",
                        resource_type="approval_request",
                        resource_id=request.id,
                        detail={"tool_name": action.tool_name, "comment": comment},
                    )
                )
                label = _decision_title(action.tool_name, decision)
                session.add(
                    IncidentTimeline(
                        incident_id=incident_id,
                        occurred_at=utcnow(),
                        event_type="approval.decided",
                        title=label,
                        detail=comment,
                        actor="human",
                    )
                )
                approved = request.status == "APPROVED"
            await self._publish(incident_id, label, "approval.decided")
            if approved:
                await self._resume_unlocked(incident_id, actor)
            else:
                await self._record_rejection(incident_id)
        return incident_id

    async def _record_rejection(self, incident_id: UUID) -> None:
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, incident_id)
            pending = await session.scalar(
                select(func.count())
                .select_from(ApprovalRequest)
                .where(
                    ApprovalRequest.incident_id == incident_id,
                    ApprovalRequest.status == "PENDING_APPROVAL",
                )
            )
            if pending:
                incident.status = "awaiting_approval"
                incident.current_activity = "Waiting for approval"
            else:
                incident.status = "investigating"
                incident.current_activity = "Remediation was not approved"
            incident.updated_at = utcnow()
        await self._publish(incident_id, "Remediation was not approved")

    async def resolve_manual(self, incident_id: UUID, actor: str) -> None:
        async with self._lock(incident_id):
            async with session_scope(self.sessions) as session:
                incident = await self._require(session, incident_id)
                if incident.status == "resolved":
                    return
                run = await self._latest_run(session, incident_id)
                if incident.status == "investigating" and run and run.status == "running":
                    raise ConflictError("Investigation is still running.")
                run_id = run.id if run else None
            if run_id is None:
                run_id = await self._open_run(incident_id)
            workspace_id = await self._workspace_id(incident_id)
            state: IncidentState = {
                "incident_id": str(incident_id),
                "run_id": str(run_id),
                "workspace_id": str(workspace_id),
                "phase": "manual",
                "actor": actor,
                "model_used": self.reasoner.name,
            }
            await self.resolution(state)
            await self.rca(state)
            await self._finish_run(incident_id, run_id)

    async def _resume_unlocked(self, incident_id: UUID, actor: str) -> None:
        async with session_scope(self.sessions) as session:
            run = await self._latest_run(session, incident_id)
            if run is None:
                run = AgentRun(
                    incident_id=incident_id,
                    graph_name="incident_response",
                    status="running",
                    model=self.reasoner.name,
                    input_tokens=0,
                    output_tokens=0,
                    started_at=utcnow(),
                )
                session.add(run)
                await session.flush()
            else:
                run.status = "running"
                run.updated_at = utcnow()
            run_id = run.id
        workspace_id = await self._workspace_id(incident_id)
        state: IncidentState = {
            "incident_id": str(incident_id),
            "run_id": str(run_id),
            "workspace_id": str(workspace_id),
            "phase": "resume",
            "actor": actor,
            "model_used": self.reasoner.name,
        }
        try:
            await self._resume_graph.ainvoke(state)
        except Exception as exc:
            logger.exception("resume_failed incident=%s", incident_id)
            await self._fail(incident_id, run_id, exc)
            return
        await self._finish_run(incident_id, run_id)

    def route_after_plan(self, state: IncidentState) -> Literal["pause", "resolve"]:
        if state.get("awaiting_approval"):
            return "pause"
        return "resolve"

    def route_after_resume(self, state: IncidentState) -> Literal["resolve", "stop"]:
        if state.get("resolved_now"):
            return "resolve"
        return "stop"

    async def event_intake(self, state: IncidentState) -> dict:
        await self._announce(state["incident_id"], "Analyzing incident")
        started = time.perf_counter()
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(state["incident_id"]))
            if looks_like_injection(incident.message):
                session.add(
                    IncidentTimeline(
                        incident_id=incident.id,
                        occurred_at=utcnow(),
                        event_type="security",
                        title="Untrusted alert text ignored",
                        detail=(
                            "The alert message contained instruction-like content. "
                            "It is stored as evidence and is not a command."
                        ),
                        actor="agent",
                    )
                )
            session.add(
                IncidentTimeline(
                    incident_id=incident.id,
                    occurred_at=utcnow(),
                    event_type="agent",
                    title="AI triage started",
                    detail=f"{incident.service} in {incident.environment}.",
                    actor="agent",
                )
            )
            await self._step(
                session,
                state,
                node="EventIntakeAgent",
                summary="Accepted the alert as data and started triage.",
                started=started,
            )
        await self._publish(state["incident_id"], "AI triage started")
        return {}

    async def triage(self, state: IncidentState) -> dict:
        await self._announce(state["incident_id"], "Classifying severity")
        started = time.perf_counter()
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(state["incident_id"]))
            severity = self.reasoner.classify_severity(
                {
                    "error_rate": incident.error_rate,
                    "environment": incident.environment,
                    "message": incident.message,
                    "event_type": incident.event_type,
                }
            )
            incident.severity = severity
            incident.model_used = self.reasoner.name
            incident.updated_at = utcnow()
            session.add(
                IncidentTimeline(
                    incident_id=incident.id,
                    occurred_at=utcnow(),
                    event_type="agent",
                    title=f"Error classified as {severity}",
                    detail="Severity uses environment and error rate. Alert prose cannot lower it.",
                    actor="agent",
                )
            )
            await self._step(
                session,
                state,
                node="TriageAgent",
                summary=f"Classified {severity} from structured alert fields.",
                started=started,
                confidence=1.0,
            )
        await self._publish(state["incident_id"], f"Error classified as {severity}")
        return {}

    async def log_analysis(self, state: IncidentState) -> dict:
        await self._announce(state["incident_id"], "Searching logs")
        started = time.perf_counter()
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(state["incident_id"]))
            step = await self._step(
                session,
                state,
                node="LogAnalysisAgent",
                summary="Searched application logs.",
                started=started,
            )
            result = await self._invoke(
                session,
                incident,
                state,
                step,
                "search_logs",
                {"service": incident.service, "environment": incident.environment},
                approved=False,
            )
            count = len(result.data.get("entries", []))
            step.summary = f"Logs analyzed. {count} lines retained as evidence."
            session.add(
                IncidentTimeline(
                    incident_id=incident.id,
                    occurred_at=utcnow(),
                    event_type="evidence",
                    title="Logs analyzed",
                    detail=result.summary,
                    actor="agent",
                )
            )
        await self._publish(state["incident_id"], "Logs analyzed")
        return {}

    async def deployment_analysis(self, state: IncidentState) -> dict:
        await self._announce(state["incident_id"], "Checking deployments")
        started = time.perf_counter()
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(state["incident_id"]))
            step = await self._step(
                session,
                state,
                node="DeploymentAnalysisAgent",
                summary="Checked recent deployments.",
                started=started,
            )
            result = await self._invoke(
                session,
                incident,
                state,
                step,
                "get_recent_deployments",
                {"service": incident.service},
                approved=False,
            )
            active = _active_version(result.data.get("deployments", []))
            title = f"Deployment {active} correlated" if active else "No deployment correlated"
            session.add(
                IncidentTimeline(
                    incident_id=incident.id,
                    occurred_at=utcnow(),
                    event_type="evidence",
                    title=title,
                    detail=result.summary,
                    actor="agent",
                )
            )
            step.summary = title
        await self._publish(state["incident_id"], title if "title" in locals() else "Deployment checked")
        return {}

    async def investigation(self, state: IncidentState) -> dict:
        await self._announce(state["incident_id"], "Inspecting GitHub commits")
        started = time.perf_counter()
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(state["incident_id"]))
            step = await self._step(
                session,
                state,
                node="InvestigationAgent",
                summary="Inspected commits and customer reports.",
                started=started,
            )
            commits = await self._invoke(
                session,
                incident,
                state,
                step,
                "get_recent_commits",
                {"service": incident.service, "limit": 5},
                approved=False,
            )
            reports = await self._invoke(
                session,
                incident,
                state,
                step,
                "search_customer_reports",
                {"service": incident.service},
                approved=False,
            )
            notable = _notable_commit(commits.data.get("commits", []))
            title = (
                f"GitHub commit {notable['sha']} identified"
                if notable
                else "No recent commit identified"
            )
            detail = notable["message"] if notable else commits.summary
            session.add(
                IncidentTimeline(
                    incident_id=incident.id,
                    occurred_at=utcnow(),
                    event_type="evidence",
                    title=title,
                    detail=detail,
                    actor="agent",
                )
            )
            report_count = len(reports.data.get("reports", []))
            if report_count:
                session.add(
                    IncidentTimeline(
                        incident_id=incident.id,
                        occurred_at=utcnow(),
                        event_type="evidence",
                        title="Customer reports correlated",
                        detail=f"{report_count} open reports match this service.",
                        actor="agent",
                    )
                )
            step.summary = title
        await self._publish(state["incident_id"], title)
        return {}

    async def historical(self, state: IncidentState) -> dict:
        await self._announce(state["incident_id"], "Searching historical incidents")
        started = time.perf_counter()
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(state["incident_id"]))
            evidence = await self._evidence(session, incident)
            query = retrieval_query(
                message=incident.message,
                service=incident.service,
                logs=evidence.logs,
                commits=evidence.commits,
            )
            step = await self._step(
                session,
                state,
                node="HistoricalIncidentAgent",
                summary="Searched prior incidents.",
                started=started,
            )
            result = await self._invoke(
                session,
                incident,
                state,
                step,
                "search_previous_incidents",
                {"query": query, "limit": 3},
                approved=False,
            )
            matches = result.data.get("incidents", [])
            top = matches[0] if matches else None
            if top and float(top.get("similarity") or 0) >= 0.35:
                title = f"Historical incident {top['external_id']} matched"
                detail = (
                    f"{top['title']} · similarity {float(top['similarity']):.2f}. "
                    f"{top.get('root_cause', '')}"
                )
            else:
                title = "No strong historical match"
                detail = result.summary
            session.add(
                IncidentTimeline(
                    incident_id=incident.id,
                    occurred_at=utcnow(),
                    event_type="evidence",
                    title=title,
                    detail=detail,
                    actor="agent",
                )
            )
            step.summary = title
        await self._publish(state["incident_id"], title)
        return {}

    async def root_cause(self, state: IncidentState) -> dict:
        await self._announce(state["incident_id"], "Generating hypothesis")
        started = time.perf_counter()
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(state["incident_id"]))
            evidence = await self._evidence(session, incident)
            evidence_ids = [
                str(value)
                for value in (
                    await session.scalars(
                        select(IncidentEvidence.id).where(
                            IncidentEvidence.incident_id == incident.id
                        )
                    )
                ).all()
            ]
            hypotheses = self.reasoner.hypothesize(evidence)
            for index, item in enumerate(hypotheses, start=1):
                session.add(
                    IncidentHypothesis(
                        incident_id=incident.id,
                        hypothesis_key=item.key,
                        title=item.title,
                        description=item.description,
                        confidence=item.confidence,
                        is_primary=item.is_primary,
                        evidence=item.evidence,
                        evidence_ids=evidence_ids,
                        rank=index,
                    )
                )
            primary = hypotheses[0]
            incident.summary = primary.description
            incident.model_used = self.reasoner.name
            incident.updated_at = utcnow()
            session.add(
                IncidentTimeline(
                    incident_id=incident.id,
                    occurred_at=utcnow(),
                    event_type="hypothesis",
                    title="Root cause hypothesis generated",
                    detail=f"{primary.title} · {int(primary.confidence * 100)}% confidence.",
                    actor="agent",
                )
            )
            await self._step(
                session,
                state,
                node="RootCauseAgent",
                summary=f"Primary hypothesis: {primary.title}.",
                started=started,
                confidence=primary.confidence,
                evidence=primary.evidence,
            )
        await self._publish(state["incident_id"], "Root cause hypothesis generated")
        return {}

    async def plan(self, state: IncidentState) -> dict:
        await self._announce(state["incident_id"], "Planning actions")
        started = time.perf_counter()
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(state["incident_id"]))
            evidence = await self._evidence(session, incident)
            hypotheses = self.reasoner.hypothesize(evidence)
            proposals = self.reasoner.plan(evidence, hypotheses)
            session.add(
                IncidentTimeline(
                    incident_id=incident.id,
                    occurred_at=utcnow(),
                    event_type="plan",
                    title="Action plan ready",
                    detail=(
                        ", ".join(item.tool_name for item in proposals)
                        if proposals
                        else "No side effects recommended."
                    ),
                    actor="agent",
                )
            )
            await self._step(
                session,
                state,
                node="ActionPlannerAgent",
                summary=(
                    f"Proposed {len(proposals)} actions."
                    if proposals
                    else "Proposed no side effects."
                ),
                started=started,
                evidence=[item.tool_name for item in proposals],
            )
            state["proposed"] = [
                {
                    "tool_name": item.tool_name,
                    "title": item.title,
                    "reason": item.reason,
                    "expected_impact": item.expected_impact,
                    "confidence": item.confidence,
                    "arguments": item.arguments,
                    "evidence": item.evidence,
                }
                for item in proposals
            ]
        await self._publish(state["incident_id"], "Action plan ready")
        return {"proposed": state.get("proposed", [])}

    async def policy_gate(self, state: IncidentState) -> dict:
        await self._announce(state["incident_id"], "Applying safety policy")
        started = time.perf_counter()
        pending = False
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(state["incident_id"]))
            known = await self._known_versions(session, incident.id)
            for proposal in state.get("proposed", []):
                decision = self.policy.evaluate(
                    proposal["tool_name"], llm_suggested_risk="LOW"
                )
                self.policy.validate_arguments(
                    proposal["tool_name"], proposal["arguments"], known_versions=known
                )
                self._assert_scope(incident, proposal["arguments"])
                status = "PENDING_APPROVAL" if decision.requires_approval else "APPROVED"
                action = IncidentAction(
                    incident_id=incident.id,
                    tool_name=proposal["tool_name"],
                    risk_level=decision.risk,
                    status=status,
                    title=proposal["title"],
                    reason=proposal["reason"],
                    expected_impact=proposal["expected_impact"],
                    confidence=proposal["confidence"],
                    arguments=proposal["arguments"],
                )
                session.add(action)
                await session.flush()
                if decision.requires_approval:
                    pending = True
                    session.add(
                        ApprovalRequest(
                            incident_id=incident.id,
                            workspace_id=incident.workspace_id,
                            agent_run_id=UUID(state["run_id"]) if state.get("run_id") else None,
                            action_id=action.id,
                            status="PENDING_APPROVAL",
                            tool_name=action.tool_name,
                            title=action.title,
                            reason=action.reason,
                            risk_level=decision.risk,
                            expected_impact=action.expected_impact,
                            confidence=action.confidence,
                            evidence=proposal["evidence"],
                            proposed_arguments=action.arguments,
                        )
                    )
            session.add(
                IncidentTimeline(
                    incident_id=incident.id,
                    occurred_at=utcnow(),
                    event_type="policy",
                    title="Policy classified proposed actions",
                    detail="Risk levels come from the policy table. The model cannot override them.",
                    actor="system",
                )
            )
            await self._step(
                session,
                state,
                node="RiskPolicyAgent",
                summary="Classified every proposed tool. External writes are pending approval."
                if pending
                else "No external writes were proposed.",
                started=started,
            )
        await self._publish(state["incident_id"], "Policy classified proposed actions")
        return {"awaiting_approval": pending}

    async def execute(self, state: IncidentState) -> dict:
        phase = state.get("phase")
        if phase == "resume":
            await self._announce(state["incident_id"], "Executing approved actions")
        started = time.perf_counter()
        mitigated = False
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(state["incident_id"]))
            if phase == "resume":
                incident.status = "executing"
                incident.updated_at = utcnow()
            actions = (
                await session.scalars(
                    select(IncidentAction).where(IncidentAction.incident_id == incident.id)
                )
            ).all()
            approved = [action for action in actions if action.status == "APPROVED"]
            step = None
            if approved or phase == "resume":
                step = await self._step(
                    session,
                    state,
                    node="ExecutionAgent",
                    summary="Executed allowlisted tools that were cleared to run.",
                    started=started,
                )
            known = await self._known_versions(session, incident.id)
            for action in approved:
                result_status = await self._execute_action(
                    session, incident, state, step, action, known
                )
                if result_status == "EXECUTED" and action.tool_name in MITIGATING_TOOLS:
                    mitigated = True
                if action.tool_name == "draft_slack_message" and result_status == "EXECUTED":
                    session.add(
                        IncidentTimeline(
                            incident_id=incident.id,
                            occurred_at=utcnow(),
                            event_type="draft",
                            title="Slack draft prepared",
                            detail="Stored locally. It was not posted.",
                            actor="agent",
                        )
                    )
                if action.tool_name == "draft_customer_email" and result_status == "EXECUTED":
                    session.add(
                        IncidentTimeline(
                            incident_id=incident.id,
                            occurred_at=utcnow(),
                            event_type="draft",
                            title="Customer email draft prepared",
                            detail="Stored locally. It was not sent.",
                            actor="agent",
                        )
                    )
                if action.tool_name in MITIGATING_TOOLS and result_status == "EXECUTED":
                    session.add(
                        IncidentTimeline(
                            incident_id=incident.id,
                            occurred_at=utcnow(),
                            event_type="execution",
                            title=f"{action.tool_name.replace('_', ' ').title()} executed",
                            detail=action.result.get("summary") if action.result else action.title,
                            actor="agent",
                        )
                    )
            if phase == "resume" and not mitigated:
                still_pending = any(action.status == "PENDING_APPROVAL" for action in actions)
                rejected = any(action.status == "REJECTED" for action in actions)
                if still_pending:
                    incident.status = "awaiting_approval"
                    incident.current_activity = "Waiting for approval"
                elif rejected:
                    incident.status = "investigating"
                    incident.current_activity = "Remediation was not approved"
                else:
                    incident.status = "investigating"
                    incident.current_activity = "Follow-up actions finished"
                incident.updated_at = utcnow()
        if phase == "resume":
            await self._publish(state["incident_id"], "Executing approved actions")
        return {"resolved_now": mitigated and phase == "resume"}

    async def human_approval(self, state: IncidentState) -> dict:
        await self._announce(state["incident_id"], "Waiting for approval")
        started = time.perf_counter()
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(state["incident_id"]))
            incident.status = "awaiting_approval"
            incident.current_activity = "Waiting for approval"
            incident.updated_at = utcnow()
            actions = (
                await session.scalars(
                    select(IncidentAction).where(
                        IncidentAction.incident_id == incident.id,
                        IncidentAction.status == "PENDING_APPROVAL",
                    )
                )
            ).all()
            for action in actions:
                title = (
                    "Rollback awaiting approval"
                    if action.tool_name == "rollback_deployment"
                    else f"{action.title} awaiting approval"
                )
                session.add(
                    IncidentTimeline(
                        incident_id=incident.id,
                        occurred_at=utcnow(),
                        event_type="approval.requested",
                        title=title,
                        detail=action.reason,
                        actor="agent",
                    )
                )
            session.add(
                WorkflowCheckpoint(
                    incident_id=incident.id,
                    run_id=UUID(state["run_id"]) if state.get("run_id") else None,
                    node_name="HumanApprovalNode",
                    status="paused",
                    state={
                        "incident_id": state["incident_id"],
                        "run_id": state.get("run_id"),
                        "awaiting_approval": True,
                    },
                )
            )
            await self._step(
                session,
                state,
                node="HumanApprovalNode",
                summary="Paused for human approval. No further tools will run until a decision.",
                started=started,
            )
        await self._publish(state["incident_id"], "Waiting for approval")
        return {"awaiting_approval": True}

    async def resolution(self, state: IncidentState) -> dict:
        await self._announce(state["incident_id"], "Resolving incident")
        started = time.perf_counter()
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(state["incident_id"]))
            if incident.status != "resolved":
                incident.status = "resolved"
                incident.resolved_at = utcnow()
                incident.current_activity = "Generating RCA"
                incident.updated_at = utcnow()
                session.add(
                    IncidentTimeline(
                        incident_id=incident.id,
                        occurred_at=utcnow(),
                        event_type="resolution",
                        title="Incident resolved",
                        detail="The investigation reached a terminal state.",
                        actor="agent" if state.get("phase") != "manual" else "human",
                    )
                )
            await self._step(
                session,
                state,
                node="ResolutionAgent",
                summary="Marked the incident resolved.",
                started=started,
            )
        await self._publish(state["incident_id"], "Incident resolved")
        return {}

    async def rca(self, state: IncidentState) -> dict:
        await self._announce(state["incident_id"], "Generating RCA")
        started = time.perf_counter()
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(state["incident_id"]))
            existing = await session.scalar(
                select(RcaReport)
                .where(RcaReport.incident_id == incident.id)
                .order_by(RcaReport.version.desc())
            )
            evidence = await self._evidence(session, incident)
            hypotheses = self.reasoner.hypothesize(evidence)
            titles = (
                await session.scalars(
                    select(IncidentTimeline.title)
                    .where(IncidentTimeline.incident_id == incident.id)
                    .order_by(IncidentTimeline.occurred_at)
                )
            ).all()
            actions = (
                await session.scalars(
                    select(IncidentAction).where(IncidentAction.incident_id == incident.id)
                )
            ).all()
            executed = [action.title for action in actions if action.status == "EXECUTED"]
            rejected = [action.title for action in actions if action.status == "REJECTED"]
            draft = self.reasoner.write_rca(
                evidence, hypotheses, list(titles), executed, rejected
            )
            summary, input_tokens, output_tokens = await maybe_rewrite_summary(
                self.settings, draft.executive_summary, evidence
            )
            draft.executive_summary = summary
            incident.input_tokens = (incident.input_tokens or 0) + input_tokens
            incident.output_tokens = (incident.output_tokens or 0) + output_tokens
            report = RcaReport(
                incident_id=incident.id,
                version=(existing.version + 1) if existing is not None else 1,
                executive_summary=draft.executive_summary,
                impact=draft.impact,
                detection=draft.detection,
                timeline_narrative=draft.timeline_narrative,
                root_cause=draft.root_cause,
                contributing_factors=draft.contributing_factors,
                resolution=draft.resolution,
                corrective_actions=draft.corrective_actions,
                preventive_actions=draft.preventive_actions,
                confidence=draft.confidence,
                evidence_sources=draft.evidence_sources,
                disclosure=(
                    "This RCA was assembled by OpsPilot from persisted incident facts and "
                    "evidence. Hypothesis scores are deterministic investigation scores, "
                    "not calibrated probabilities."
                ),
                html="",
            )
            report.html = render_rca_html(incident, report)
            session.add(report)
            await self._remember(session, incident, draft.root_cause, draft.resolution)
            incident.current_activity = "Resolved"
            incident.model_used = self.settings.reasoning_model
            incident.updated_at = utcnow()
            session.add(
                IncidentTimeline(
                    incident_id=incident.id,
                    occurred_at=utcnow(),
                    event_type="rca",
                    title="RCA generated",
                    detail="Structured report stored. HTML export is available.",
                    actor="agent",
                )
            )
            await self._step(
                session,
                state,
                node="RCAAgent",
                summary="Wrote the RCA from evidence, actions, and the timeline.",
                started=started,
            )
        await self._publish(state["incident_id"], "RCA generated")
        return {}

    async def _execute_action(
        self,
        session: AsyncSession,
        incident: Incident,
        state: IncidentState,
        step: AgentStep | None,
        action: IncidentAction,
        known: set[str],
    ) -> str:
        if action.status in {"EXECUTED", "SUCCEEDED", "FAILED", "CANCELLED"}:
            return action.status
        if action.status == "EXECUTING" and action.execution_id is not None:
            return action.status
        if action.execution_id is not None:
            return action.status
        action.status = "EXECUTING"
        action.execution_id = uuid4()
        action.executed_at = utcnow()
        action.attempt_count = (action.attempt_count or 0) + 1
        action.idempotency_key = action.idempotency_key or str(action.execution_id)
        from app.integrations.catalog import RETRY_CLASS

        action.retry_class = RETRY_CLASS.get(action.tool_name, "DO_NOT_RETRY")
        try:
            self._validate_action(incident, action.tool_name, dict(action.arguments))
            result = await self._invoke(
                session,
                incident,
                state,
                step,
                action.tool_name,
                dict(action.arguments),
                approved=True,
                known_versions=known,
                idempotency_key=action.idempotency_key or "",
            )
            action.status = "EXECUTED" if result.status == "EXECUTED" else "FAILED"
            action.result = {"summary": result.summary, **result.data}
            action.provider_ref = str(result.data.get("external_url") or result.data.get("provider_message_id") or "")
            action.last_error = None if action.status == "EXECUTED" else redact(result.summary)
        except (PolicyViolation, ValidationError) as exc:
            action.status = "FAILED"
            action.last_error = redact(str(exc))
            action.result = {"error": redact(str(exc))}
            session.add(
                ToolCall(
                    incident_id=incident.id,
                    run_id=UUID(state["run_id"]) if state.get("run_id") else None,
                    step_id=step.id if step else None,
                    tool_name=action.tool_name,
                    risk_level=action.risk_level,
                    arguments=dict(action.arguments),
                    result_summary=redact(str(exc)),
                    result={"error": redact(str(exc))},
                    status="FAILED",
                    latency_ms=0,
                )
            )
        action.updated_at = utcnow()
        session.add(
            AuditLog(
                incident_id=incident.id,
                actor=state.get("actor") or "policy",
                action=f"tool_{action.status.lower()}",
                resource_type="incident_action",
                resource_id=action.id,
                detail={"tool_name": action.tool_name},
            )
        )
        return action.status

    def _validate_action(self, incident: Incident, tool_name: str, arguments: dict) -> None:
        spec = self.tools.get(tool_name)
        spec.args_model.model_validate(arguments)
        self._assert_scope(incident, arguments)

    def _assert_scope(self, incident: Incident, arguments: dict) -> None:
        service = arguments.get("service")
        if service and service != incident.service:
            raise PolicyViolation("Action service does not match the incident.")
        environment = arguments.get("environment")
        if environment and environment != incident.environment:
            raise PolicyViolation("Action environment does not match the incident.")

    async def _invoke(
        self,
        session: AsyncSession,
        incident: Incident,
        state: IncidentState,
        step: AgentStep | None,
        tool_name: str,
        arguments: dict,
        *,
        approved: bool,
        known_versions: set[str] | None = None,
        idempotency_key: str = "",
    ):
        decision = self.policy.authorize(tool_name, "APPROVED" if approved else None)
        known = known_versions if known_versions is not None else set()
        if known_versions is None and tool_name == "rollback_deployment":
            known = await self._known_versions(session, incident.id)
        self.policy.validate_arguments(tool_name, arguments, known_versions=known)
        spec = self.tools.get(tool_name)
        parsed = spec.args_model.model_validate(arguments)
        context = ToolContext(
            mode=self.settings.mode,
            incident_id=incident.id,
            workspace_id=incident.workspace_id,
            scenario_key=incident.scenario_key,
            service=incident.service,
            environment=incident.environment,
            started_at=incident.started_at,
            settings=self.settings,
            session=session,
            integrations=self.integrations,
            idempotency_key=idempotency_key,
        )
        clock = time.perf_counter()
        result = await asyncio.wait_for(spec.handler(parsed, context), timeout=spec.timeout_seconds)
        session.add(
            ToolCall(
                incident_id=incident.id,
                run_id=UUID(state["run_id"]) if state.get("run_id") else None,
                step_id=step.id if step else None,
                tool_name=tool_name,
                risk_level=decision.risk,
                arguments=arguments,
                result_summary=result.summary,
                result=result.data,
                status=result.status,
                latency_ms=int((time.perf_counter() - clock) * 1000),
            )
        )
        await persist_tool_evidence(session, incident, tool_name, result)
        return result

    async def _evidence(self, session: AsyncSession, incident: Incident) -> Evidence:
        calls = (
            await session.scalars(
                select(ToolCall)
                .where(ToolCall.incident_id == incident.id)
                .order_by(ToolCall.created_at)
            )
        ).all()

        def payload(name: str) -> dict:
            for call in reversed(calls):
                if call.tool_name == name and call.status == "EXECUTED":
                    return call.result or {}
            return {}

        return Evidence(
            event={
                "service": incident.service,
                "environment": incident.environment,
                "event_type": incident.event_type,
                "error_rate": incident.error_rate,
                "message": incident.message,
                "started_at": incident.started_at.isoformat(),
                "incident_number": incident.incident_number,
            },
            logs=list(payload("search_logs").get("entries", [])),
            deployments=list(payload("get_recent_deployments").get("deployments", [])),
            commits=list(payload("get_recent_commits").get("commits", [])),
            related_incidents=list(payload("search_previous_incidents").get("incidents", [])),
            customer_reports=list(payload("search_customer_reports").get("reports", [])),
        )

    async def _known_versions(self, session: AsyncSession, incident_id: UUID) -> set[str]:
        calls = (
            await session.scalars(
                select(ToolCall)
                .where(
                    ToolCall.incident_id == incident_id,
                    ToolCall.tool_name == "get_recent_deployments",
                )
                .order_by(ToolCall.created_at.desc())
            )
        ).all()
        versions: set[str] = set()
        for call in calls:
            for item in (call.result or {}).get("deployments", []):
                if item.get("version"):
                    versions.add(str(item["version"]))
        return versions

    async def _remember(
        self, session: AsyncSession, incident: Incident, root_cause: str, resolution: str
    ) -> None:
        existing = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.workspace_id == incident.workspace_id,
                KnowledgeDocument.external_id == incident.incident_number,
            )
        )
        if existing is not None:
            return
        document = KnowledgeDocument(
            workspace_id=incident.workspace_id,
            source_type="prior_incident",
            external_id=incident.incident_number,
            title=incident.title,
            service=incident.service,
            symptoms=incident.message,
            root_cause=root_cause,
            resolution=resolution,
            timeline_text=incident.summary or "",
            meta={"source": "resolved_incident"},
        )
        session.add(document)
        await session.flush()
        await session.execute(
            text(
                """
                INSERT INTO incident_embeddings (id, document_id, embedding, model, created_at)
                VALUES (:id, :document_id, CAST(:embedding AS vector), :model, now())
                """
            ),
            {
                "id": uuid4(),
                "document_id": document.id,
                "embedding": vector_literal(embed(f"{document.symptoms}\n{document.root_cause}")),
                "model": MODEL_NAME,
            },
        )

    async def _announce(self, incident_id: str, activity: str) -> None:
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, UUID(incident_id))
            incident.current_activity = activity
            incident.updated_at = utcnow()
        await self._publish(incident_id, activity)
        delay = max(self.settings.step_delay_ms, 0) / 1000
        if delay:
            await asyncio.sleep(delay)

    async def _publish(
        self,
        incident_id: UUID | str,
        title: str,
        event_type: str = "incident.updated",
    ) -> None:
        workspace_id = await self._workspace_id(UUID(str(incident_id)))
        await self.bus.publish(
            {
                "workspace_id": str(workspace_id),
                "incident_id": str(incident_id),
                "type": event_type,
                "title": title,
            }
        )

    async def _workspace_id(self, incident_id: UUID) -> UUID:
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, incident_id)
            return incident.workspace_id

    async def _step(
        self,
        session: AsyncSession,
        state: IncidentState,
        *,
        node: str,
        summary: str,
        started: float,
        status: str = "completed",
        evidence: list | None = None,
        confidence: float | None = None,
        error: str | None = None,
    ) -> AgentStep:
        run_id = UUID(state["run_id"])
        current = await session.scalar(
            select(func.max(AgentStep.sequence)).where(AgentStep.run_id == run_id)
        )
        latency = int((time.perf_counter() - started) * 1000)
        step = AgentStep(
            run_id=run_id,
            incident_id=UUID(state["incident_id"]),
            node_name=node,
            sequence=(current or 0) + 1,
            status=status,
            summary=summary,
            evidence=evidence,
            confidence=confidence,
            latency_ms=latency,
            error=error,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        session.add(step)
        await session.flush()
        incident = await self._require(session, UUID(state["incident_id"]))
        incident.execution_time_ms = (incident.execution_time_ms or 0) + latency
        return step

    async def _require(self, session: AsyncSession, incident_id: UUID) -> Incident:
        incident = await session.get(Incident, incident_id)
        if incident is None:
            raise NotFoundError("Incident not found.")
        return incident

    async def _open_run(self, incident_id: UUID) -> UUID:
        async with session_scope(self.sessions) as session:
            run = AgentRun(
                incident_id=incident_id,
                graph_name="incident_response",
                status="running",
                model=self.reasoner.name,
                input_tokens=0,
                output_tokens=0,
                started_at=utcnow(),
            )
            session.add(run)
            await session.flush()
            return run.id

    async def _latest_run(self, session: AsyncSession, incident_id: UUID) -> AgentRun | None:
        return await session.scalar(
            select(AgentRun)
            .where(AgentRun.incident_id == incident_id)
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )

    async def _finish_run(self, incident_id: UUID, run_id: UUID) -> None:
        async with session_scope(self.sessions) as session:
            incident = await self._require(session, incident_id)
            run = await session.get(AgentRun, run_id)
            if run is None:
                return
            latency = await session.scalar(
                select(func.coalesce(func.sum(AgentStep.latency_ms), 0)).where(
                    AgentStep.run_id == run_id
                )
            )
            run.latency_ms = int(latency or 0)
            run.input_tokens = incident.input_tokens
            run.output_tokens = incident.output_tokens
            run.model = incident.model_used or run.model
            run.updated_at = utcnow()
            if incident.status == "awaiting_approval":
                run.status = "paused"
            else:
                run.status = "completed"
                run.finished_at = utcnow()

    async def _fail(self, incident_id: UUID, run_id: UUID, exc: Exception) -> None:
        message = redact(str(exc))
        async with session_scope(self.sessions) as session:
            incident = await session.get(Incident, incident_id)
            run = await session.get(AgentRun, run_id)
            if incident is not None and incident.status != "resolved":
                incident.last_error = message
                incident.current_activity = "Investigation failed"
                incident.updated_at = utcnow()
                session.add(
                    IncidentTimeline(
                        incident_id=incident.id,
                        occurred_at=utcnow(),
                        event_type="error",
                        title="Investigation failed",
                        detail=message,
                        actor="system",
                    )
                )
            if run is not None:
                run.status = "failed"
                run.error = message
                run.finished_at = utcnow()
                run.updated_at = utcnow()
        await self._publish(incident_id, "Investigation failed")


def _active_version(deployments: list[dict]) -> str | None:
    for item in deployments:
        if item.get("status") == "active":
            return str(item.get("version"))
    if deployments:
        return str(deployments[0].get("version"))
    return None


def _notable_commit(commits: list[dict]) -> dict | None:
    return commits[0] if commits else None


def _decision_title(tool_name: str, decision: str) -> str:
    verb = {"APPROVED": "approved", "REJECTED": "rejected", "MODIFIED": "modified"}[decision]
    if tool_name == "rollback_deployment":
        return f"Rollback {verb}"
    return f"{tool_name.replace('_', ' ').title()} {verb}"
