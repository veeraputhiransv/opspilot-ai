"""Objects created at startup and stored on app.state."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.workflow import IncidentWorkflow
from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.events.bus import EventBus
from app.identity.service import AuthService
from app.services.event_service import EventService
from app.services.integrations import IntegrationService
from app.services.query_service import QueryService
from app.services.stream_tickets import StreamTicketService
from app.services.vault import SecretVaultService
from app.workers.runner import IncidentWorker


@dataclass
class AppContext:
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    bus: EventBus
    workflow: IncidentWorkflow
    worker: IncidentWorker
    events: EventService
    queries: QueryService
    auth: AuthService
    limiter: RateLimiter
    vault: SecretVaultService
    tickets: StreamTicketService
    integrations: IntegrationService
    redis: Any | None
