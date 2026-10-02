"""FastAPI application factory."""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.agents.workflow import IncidentWorkflow
from app.api.auth import router as auth_router
from app.api.router import router
from app.core.config import get_settings
from app.core.errors import OpsPilotError, RateLimitError
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimiter
from app.db import create_engine, create_session_factory
from app.events.bus import EventBus
from app.identity.service import AuthService
from app.runtime import AppContext
from app.seed.bootstrap import bootstrap
from app.services.event_service import EventService
from app.services.integrations import IntegrationService
from app.services.query_service import QueryService
from app.services.stream_tickets import StreamTicketService
from app.services.vault import SecretVaultService
from app.workers.runner import IncidentWorker

logger = logging.getLogger("opspilot.api")


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.log_level)
        engine = create_engine(settings.database_url)
        sessions = create_session_factory(engine)
        bus = EventBus()
        await bus.connect(settings.redis_url)
        redis: Any | None = getattr(bus, "_pub", None)
        limiter = RateLimiter()
        limiter.bind_redis(redis)
        vault = SecretVaultService(settings)
        tickets = StreamTicketService(redis, settings.stream_ticket_seconds)
        integrations = IntegrationService(sessions, settings, vault)
        workflow = IncidentWorkflow(settings, sessions, bus, integrations)
        worker = IncidentWorker(workflow)
        context = AppContext(
            settings=settings,
            engine=engine,
            sessions=sessions,
            bus=bus,
            workflow=workflow,
            worker=worker,
            events=EventService(sessions, bus, worker, settings),
            queries=QueryService(sessions),
            auth=AuthService(sessions, settings),
            limiter=limiter,
            vault=vault,
            tickets=tickets,
            integrations=integrations,
            redis=redis,
        )
        app.state.ctx = context
        await bootstrap(sessions, settings)
        logger.info("opspilot_ready mode=%s", settings.mode)
        yield
        await worker.drain()
        await bus.close()
        await engine.dispose()

    app = FastAPI(
        title="OpsPilot AI",
        version="1.0.0",
        summary="Autonomous incident response and operations agent",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(router)

    @app.exception_handler(OpsPilotError)
    async def handle_opspilot_error(_request: Request, exc: OpsPilotError) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimitError):
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message}},
            headers=headers,
        )

    @app.get("/health")
    async def root_health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    async def ready(request: Request) -> JSONResponse:
        ctx: AppContext | None = getattr(request.app.state, "ctx", None)
        database = "unavailable"
        redis = "unavailable"
        if ctx is not None:
            try:
                async with ctx.sessions() as session:
                    await session.execute(text("SELECT 1"))
                database = "ok"
            except Exception:
                database = "unavailable"
            if ctx.redis is not None:
                try:
                    await ctx.redis.ping()
                    redis = "ok"
                except Exception:
                    redis = "unavailable"
            elif not ctx.bus._redis_ok:
                redis = "optional"
        status = "ok" if database == "ok" else "not_ready"
        code = 200 if status == "ok" else 503
        return JSONResponse(
            {"status": status, "database": database, "redis": redis},
            status_code=code,
        )

    return app


app = create_app()
