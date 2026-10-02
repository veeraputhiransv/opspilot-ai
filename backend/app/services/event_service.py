"""Turn a webhook into an incident and hand it to the worker."""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db import session_scope
from app.events.bus import EventBus
from app.identity.context import AuthContext
from app.integrations.demo_data import detect_scenario, scenario_title
from app.models import AuditLog, Incident, IncidentEvent, IncidentTimeline
from app.models.base import utcnow
from app.schemas.api import EventIn, IncidentCreated
from app.services.ingest_keys import ingest_idempotency_key
from app.workers.runner import IncidentWorker


class EventService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        bus: EventBus,
        worker: IncidentWorker,
        settings: Settings,
    ) -> None:
        self.sessions = sessions
        self.bus = bus
        self.worker = worker
        self.settings = settings

    async def ingest(self, event: EventIn, auth: AuthContext) -> IncidentCreated:
        scenario = detect_scenario(event.model_dump())
        key = ingest_idempotency_key(auth.workspace_id, event)
        async with session_scope(self.sessions) as session:
            existing = await session.scalar(
                select(IncidentEvent).where(
                    IncidentEvent.workspace_id == auth.workspace_id,
                    IncidentEvent.idempotency_key == key,
                )
            )
            if existing is not None:
                incident = await session.get(Incident, existing.incident_id)
                if incident is None:
                    raise RuntimeError("Idempotent event is missing its incident.")
                return IncidentCreated(
                    id=incident.id,
                    incident_number=incident.incident_number,
                    status=incident.status,
                    replayed=True,
                    idempotency_key=key,
                )
            allocated = await session.execute(
                text(
                    "INSERT INTO workspace_incident_counters (workspace_id, next_number) "
                    "VALUES (:workspace_id, 1025) "
                    "ON CONFLICT (workspace_id) DO UPDATE "
                    "SET next_number = workspace_incident_counters.next_number + 1 "
                    "RETURNING next_number"
                ),
                {"workspace_id": auth.workspace_id},
            )
            number = int(allocated.scalar_one()) - 1
            now = utcnow()
            started = event.timestamp or now
            incident = Incident(
                organization_id=auth.organization_id,
                workspace_id=auth.workspace_id,
                incident_number=f"INC-{number:04d}",
                service=event.service,
                environment=event.environment,
                event_type=event.event_type,
                scenario_key=scenario,
                status="investigating",
                title=scenario_title(scenario),
                summary=event.message,
                message=event.message,
                error_rate=event.error_rate,
                current_activity="Event received",
                model_used=self.settings.reasoning_model,
                started_at=started,
            )
            session.add(incident)
            await session.flush()
            session.add(
                IncidentEvent(
                    workspace_id=auth.workspace_id,
                    incident_id=incident.id,
                    idempotency_key=key,
                    source="webhook" if auth.via == "api_key" else "console",
                    payload=event.model_dump(mode="json"),
                    received_at=now,
                )
            )
            session.add(
                IncidentTimeline(
                    incident_id=incident.id,
                    occurred_at=now,
                    event_type="incident.created",
                    title="Alert received",
                    detail=(
                        f"{event.service} {event.environment} · {event.event_type} · "
                        f"error rate {event.error_rate:g}%"
                    ),
                    actor="system",
                )
            )
            session.add(
                AuditLog(
                    organization_id=auth.organization_id,
                    workspace_id=auth.workspace_id,
                    actor_user_id=auth.user_id,
                    actor_type=auth.via,
                    incident_id=incident.id,
                    actor=auth.actor_label,
                    action="event_ingested",
                    resource_type="incident",
                    resource_id=incident.id,
                    detail={"scenario_key": scenario, "service": event.service, "idempotency_key": key},
                )
            )
            created = IncidentCreated(
                id=incident.id,
                incident_number=incident.incident_number,
                status=incident.status,
                replayed=False,
                idempotency_key=key,
            )
        await self.bus.publish(
            {
                "workspace_id": str(auth.workspace_id),
                "incident_id": str(created.id),
                "type": "incident.created",
                "title": "Alert received",
            }
        )
        self.worker.enqueue(created.id)
        return created
