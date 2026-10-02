"""Load memory, sample reports, and closed incidents on an empty database."""

from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.integrations.demo_data import evidence_for, scenario_catalog
from app.models import (
    AgentRun,
    CustomerReport,
    Incident,
    IncidentAction,
    IncidentHypothesis,
    IncidentTimeline,
    KnowledgeDocument,
    RcaReport,
)
from app.models.base import utcnow
from app.rag.corpus import CORPUS
from app.rag.embeddings import MODEL_NAME, embed, vector_literal
from app.services.rca_document import render_rca_html


async def bootstrap(sessions: async_sessionmaker[AsyncSession], settings: Settings | None = None) -> None:
    del sessions
    if settings is not None and settings.bootstrap_enabled:
        # Historical corpus seeding is phase 23 (demo workspace), not default runtime.
        return

_HISTORY: list[dict[str, Any]] = [
    {
        "number": "INC-0087",
        "service": "payment-service",
        "event_type": "error_rate_spike",
        "scenario_key": "db_pool",
        "severity": "SEV-1",
        "title": "Payment service connection pool exhaustion",
        "message": "Database connection timeout",
        "error_rate": 68,
        "summary": "A deploy reduced the Postgres pool and checkout requests timed out.",
        "hours_ago": 280,
        "minutes": 14,
        "cause": "DB Connection Pool Exhaustion",
        "key": "db_pool",
        "tool": "rollback_deployment",
        "action": "Rollback payment-service from v2.4.2 to v2.4.1",
    },
    {
        "number": "INC-0094",
        "service": "payment-service",
        "event_type": "upstream_latency",
        "scenario_key": "stripe",
        "severity": "SEV-2",
        "title": "Stripe upstream latency",
        "message": "Stripe API latency elevated",
        "error_rate": 36,
        "summary": "Payment intents stalled on Stripe. The local pool stayed healthy.",
        "hours_ago": 120,
        "minutes": 42,
        "cause": "Stripe API Latency",
        "key": "stripe",
        "tool": "create_github_issue",
        "action": "Open tracking issue for Stripe API Latency",
    },
    {
        "number": "INC-0102",
        "service": "cache-service",
        "event_type": "dependency_down",
        "scenario_key": "redis",
        "severity": "SEV-1",
        "title": "Redis dependency outage",
        "message": "Redis connection refused",
        "error_rate": 81,
        "summary": "cache-service could not open connections to Redis.",
        "hours_ago": 70,
        "minutes": 9,
        "cause": "Redis Outage",
        "key": "redis",
        "tool": "restart_service",
        "action": "Restart cache-service",
    },
    {
        "number": "INC-0115",
        "service": "payment-service",
        "event_type": "error_rate_spike",
        "scenario_key": "false_positive",
        "severity": "SEV-4",
        "title": "Transient error-rate flap",
        "message": "Brief latency flap recovered in 10s",
        "error_rate": 1.1,
        "summary": "The detector fired and the error rate recovered inside one window.",
        "hours_ago": 30,
        "minutes": 3,
        "cause": "False-positive alert",
        "key": "false_positive",
        "tool": None,
        "action": None,
    },
]


async def _seed_knowledge(session: AsyncSession) -> None:
    for document in CORPUS:
        existing = await session.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.external_id == document["external_id"])
        )
        if existing is not None:
            continue
        row = KnowledgeDocument(
            external_id=document["external_id"],
            title=document["title"],
            service=document["service"],
            symptoms=document["symptoms"],
            root_cause=document["root_cause"],
            resolution=document["resolution"],
            timeline_text=document["timeline_text"],
            meta={"source": "corpus"},
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


async def _seed_reports(session: AsyncSession) -> None:
    started = utcnow()
    for scenario in scenario_catalog():
        bundle = evidence_for(scenario["key"], started)
        for report in bundle["customer_reports"]:
            existing = await session.scalar(
                select(CustomerReport).where(CustomerReport.external_ref == report["external_ref"])
            )
            if existing is not None:
                continue
            session.add(
                CustomerReport(
                    service=report["service"],
                    title=report["title"],
                    body=report["body"],
                    source=report["source"],
                    external_ref=report["external_ref"],
                )
            )


async def _seed_history(session: AsyncSession) -> None:
    now = utcnow()
    for spec in _HISTORY:
        existing = await session.scalar(
            select(Incident).where(Incident.incident_number == spec["number"])
        )
        if existing is not None:
            continue
        started = now - timedelta(hours=int(spec["hours_ago"]))
        resolved = started + timedelta(minutes=int(spec["minutes"]))
        incident = Incident(
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
            html="",
        )
        report.html = render_rca_html(incident, report)
        session.add(report)
