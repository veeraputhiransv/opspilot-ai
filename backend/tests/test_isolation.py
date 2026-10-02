"""Postgres-backed workspace isolation and ingest auth.

Requires a migrated database. CI sets OPSPILOT_DATABASE_URL before pytest.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import create_app

pytestmark = pytest.mark.asyncio

SKIP_REASON = "OPSPILOT_DATABASE_URL is not set"


def _db_configured() -> bool:
    return bool(os.environ.get("OPSPILOT_DATABASE_URL") or os.environ.get("CI"))


@pytest.fixture
async def client():
    if not _db_configured():
        pytest.skip(SKIP_REASON)
    get_settings.cache_clear()
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as session:
            yield session
    get_settings.cache_clear()


async def _register(client: AsyncClient, suffix: str) -> dict:
    email = f"operator-{suffix}-{uuid4().hex[:10]}@example.com"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Ops Engineer",
            "organization_name": f"Org {suffix}",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    body["email"] = email
    return body


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _event(idempotency_key: str | None = None) -> dict:
    payload = {
        "service": "payment-service",
        "environment": "production",
        "event_type": "error_rate_spike",
        "error_rate": 22.0,
        "message": "checkout 5xx rate exceeded the page threshold",
    }
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    return payload


async def test_valid_event_creates_incident(client: AsyncClient) -> None:
    user = await _register(client, "valid")
    response = await client.post("/api/v1/events", headers=_auth(user["access_token"]), json=_event())
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["replayed"] is False
    assert body["incident_number"].startswith("INC-")


async def test_duplicate_ingest_does_not_open_a_second_incident(client: AsyncClient) -> None:
    user = await _register(client, "dup")
    key = f"retry-{uuid4().hex}"
    first = await client.post(
        "/api/v1/events", headers=_auth(user["access_token"]), json=_event(key)
    )
    second = await client.post(
        "/api/v1/events", headers=_auth(user["access_token"]), json=_event(key)
    )
    assert first.status_code == 202
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["replayed"] is True
    listed = await client.get("/api/v1/incidents", headers=_auth(user["access_token"]))
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


async def test_malformed_event_is_rejected(client: AsyncClient) -> None:
    user = await _register(client, "bad")
    response = await client.post(
        "/api/v1/events",
        headers=_auth(user["access_token"]),
        json={"service": "no", "environment": "prod", "event_type": "x", "error_rate": 200, "message": "x"},
    )
    assert response.status_code == 422


async def test_invalid_workspace_key_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/events",
        headers={"Authorization": "Bearer ops_live_not-a-real-key-value"},
        json=_event(),
    )
    assert response.status_code == 401


async def test_revoked_key_cannot_ingest(client: AsyncClient) -> None:
    user = await _register(client, "revoke")
    created = await client.post(
        "/api/v1/auth/api-keys",
        headers=_auth(user["access_token"]),
        json={"name": "ingest"},
    )
    assert created.status_code == 200, created.text
    raw = created.json()["key"]
    listed = await client.get("/api/v1/auth/api-keys", headers=_auth(user["access_token"]))
    key_id = listed.json()[0]["id"]
    revoked = await client.post(
        f"/api/v1/auth/api-keys/{key_id}/revoke", headers=_auth(user["access_token"])
    )
    assert revoked.status_code == 200
    response = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {raw}"},
        json=_event(f"after-revoke-{uuid4().hex}"),
    )
    assert response.status_code == 401


async def test_cross_workspace_incident_is_not_found(client: AsyncClient) -> None:
    alice = await _register(client, "alice")
    bob = await _register(client, "bob")
    created = await client.post(
        "/api/v1/events", headers=_auth(alice["access_token"]), json=_event()
    )
    incident_id = created.json()["id"]
    foreign = await client.get(
        f"/api/v1/incidents/{incident_id}", headers=_auth(bob["access_token"])
    )
    assert foreign.status_code == 404
    search = await client.post(
        "/api/v1/knowledge/search",
        headers=_auth(bob["access_token"]),
        json={"query": "checkout latency", "limit": 5},
    )
    assert search.status_code == 200
    assert search.json() == []


async def test_ingest_api_key_is_workspace_bound(client: AsyncClient) -> None:
    alice = await _register(client, "key-a")
    bob = await _register(client, "key-b")
    created = await client.post(
        "/api/v1/auth/api-keys",
        headers=_auth(alice["access_token"]),
        json={"name": "alice-ingest"},
    )
    raw = created.json()["key"]
    ingested = await client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {raw}"},
        json=_event(f"key-bound-{uuid4().hex}"),
    )
    assert ingested.status_code == 202
    incident_id = ingested.json()["id"]
    alice_view = await client.get(
        f"/api/v1/incidents/{incident_id}", headers=_auth(alice["access_token"])
    )
    bob_view = await client.get(
        f"/api/v1/incidents/{incident_id}", headers=_auth(bob["access_token"])
    )
    assert alice_view.status_code == 200
    assert bob_view.status_code == 404


async def test_stream_ticket_is_workspace_bound(client: AsyncClient) -> None:
    alice = await _register(client, "sse-a")
    bob = await _register(client, "sse-b")
    ticket = await client.post(
        "/api/v1/realtime/tickets",
        headers=_auth(alice["access_token"]),
        json={},
    )
    assert ticket.status_code == 200, ticket.text
    raw = ticket.json()["ticket"]
    expired = await client.get("/api/v1/events/stream?ticket=not-a-valid-ticket-value")
    assert expired.status_code == 401
    bob_incident = await client.post(
        "/api/v1/events", headers=_auth(bob["access_token"]), json=_event()
    )
    foreign = await client.get(
        f"/api/v1/events/stream?ticket={raw}&incident_id={bob_incident.json()['id']}"
    )
    assert foreign.status_code in {403, 404}


async def test_integration_connect_redacts_secrets(client: AsyncClient) -> None:
    user = await _register(client, "vault")
    connected = await client.post(
        "/api/v1/integrations/github/connect",
        headers=_auth(user["access_token"]),
        json={
            "provider": "github",
            "display_name": "GitHub",
            "secrets": {"token": "ghp_super_secret_value"},
            "configuration": {"allowed_repos": ["acme/payments"]},
        },
    )
    assert connected.status_code == 200, connected.text
    body = connected.json()
    assert "ghp_super_secret_value" not in str(body)
    listed = await client.get("/api/v1/integrations", headers=_auth(user["access_token"]))
    assert listed.status_code == 200
    assert "ghp_super_secret_value" not in listed.text
    other = await _register(client, "vault-b")
    other_list = await client.get("/api/v1/integrations", headers=_auth(other["access_token"]))
    github = next(item for item in other_list.json()["connections"] if item["provider"] == "github")
    assert github["status"] == "DISCONNECTED"
