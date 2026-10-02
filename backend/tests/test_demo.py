"""AcmeFlow demo seed, restricted session, and hero scenario trigger."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db import create_engine, create_session_factory, session_scope
from app.main import create_app
from app.models import KnowledgeDocument
from app.models.identity import Workspace
from app.seed.constants import DEMO_WORKSPACE_SLUG
from app.seed.demo import reset_demo, seed_demo

pytestmark = pytest.mark.asyncio

SKIP_REASON = "OPSPILOT_DATABASE_URL is not set"


def _db_configured() -> bool:
    return bool(os.environ.get("OPSPILOT_DATABASE_URL") or os.environ.get("CI"))


@pytest.fixture
async def demo_client(monkeypatch: pytest.MonkeyPatch):
    if not _db_configured():
        pytest.skip(SKIP_REASON)
    monkeypatch.setenv("OPSPILOT_DEMO_SEED_ENABLED", "true")
    monkeypatch.setenv("OPSPILOT_DEMO_PASSWORD", "AcmeFlow-operator-12")
    get_settings.cache_clear()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with session_scope(app.state.ctx.sessions) as session:
            await seed_demo(session, app.state.ctx.settings)
            await reset_demo(session, app.state.ctx.settings)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as session:
            yield session
    get_settings.cache_clear()


async def test_demo_login_and_trigger_uses_real_ingest(demo_client: AsyncClient) -> None:
    status = await demo_client.get("/api/v1/auth/demo/status")
    assert status.status_code == 200
    assert status.json()["available"] is True
    login = await demo_client.post("/api/v1/auth/demo")
    assert login.status_code == 200, login.text
    tokens = login.json()
    assert tokens["roles"] == ["operator"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = await demo_client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    body = me.json()
    assert body["full_name"] == "Alex Morgan"
    assert body["demo"] is True
    assert body["workspaces"][0]["role"] == "operator"
    created = await demo_client.post("/api/v1/demo/scenarios/db_pool/trigger", headers=headers)
    assert created.status_code == 202, created.text
    incident = created.json()
    assert incident["incident_number"].startswith("INC-")
    detail = await demo_client.get(f"/api/v1/incidents/{incident['id']}", headers=headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["title"] == "Payment API Error Rate Spike"
    assert payload["service"] == "payment-service"
    assert payload["environment"] == "production"


async def test_demo_session_cannot_connect_integrations(demo_client: AsyncClient) -> None:
    login = await demo_client.post("/api/v1/auth/demo")
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = await demo_client.post(
        "/api/v1/integrations/github/connect",
        headers=headers,
        json={
            "provider": "github",
            "display_name": "GitHub",
            "secrets": {"token": "should-not-store"},
            "configuration": {},
        },
    )
    assert response.status_code == 403
    keys = await demo_client.post(
        "/api/v1/auth/api-keys",
        headers=headers,
        json={"name": "should-fail"},
    )
    assert keys.status_code == 403


async def test_regular_workspace_cannot_trigger_demo_scenario(demo_client: AsyncClient) -> None:
    registered = await demo_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ops-{uuid4().hex[:10]}@example.com",
            "password": "correct-horse-battery",
            "full_name": "Ops Engineer",
            "organization_name": "Northwind",
        },
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    response = await demo_client.post("/api/v1/demo/scenarios/db_pool/trigger", headers=headers)
    assert response.status_code == 403


async def test_reset_demo_purges_transient_knowledge(demo_client: AsyncClient) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    try:
        async with session_scope(sessions) as session:
            workspace = await session.scalar(select(Workspace).where(Workspace.slug == DEMO_WORKSPACE_SLUG))
            assert workspace is not None
            session.add(
                KnowledgeDocument(
                    workspace_id=workspace.id,
                    external_id="INC-1999",
                    title="Transient leftover incident",
                    service="payment-service",
                    symptoms="error rate spike",
                    root_cause="self match",
                    resolution="should be purged",
                    timeline_text="leftover from a previous demo run",
                )
            )
            await session.flush()
            result = await reset_demo(session, settings)
            leftover = await session.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.workspace_id == workspace.id,
                    KnowledgeDocument.external_id == "INC-1999",
                )
            )
            kept = await session.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.workspace_id == workspace.id,
                    KnowledgeDocument.external_id == "INC-0087",
                )
            )
        assert result["removed_knowledge_documents"] >= 1
        assert leftover is None
        assert kept is not None
    finally:
        await engine.dispose()


async def test_seed_refuses_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    if not _db_configured():
        pytest.skip(SKIP_REASON)
    monkeypatch.setenv("OPSPILOT_DEMO_SEED_ENABLED", "false")
    get_settings.cache_clear()
    app = create_app()
    async with app.router.lifespan_context(app):
        from app.core.errors import ForbiddenError

        with pytest.raises(ForbiddenError):
            async with session_scope(app.state.ctx.sessions) as session:
                await seed_demo(session, app.state.ctx.settings)
    get_settings.cache_clear()
