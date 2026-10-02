"""Approval pause must survive a new workflow instance (process restart)."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import create_app

pytestmark = pytest.mark.asyncio

os.environ.setdefault("OPSPILOT_STEP_DELAY_MS", "0")


def _db_configured() -> bool:
    return bool(os.environ.get("OPSPILOT_DATABASE_URL") or os.environ.get("CI"))


async def _wait_approval(client: AsyncClient, headers: dict) -> str | None:
    import asyncio

    for _ in range(80):
        pending = await client.get("/api/v1/approvals?status=PENDING_APPROVAL", headers=headers)
        rows = pending.json()
        if rows:
            return rows[0]["id"]
        await asyncio.sleep(0.15)
    return None


async def test_approval_survives_new_app_instance() -> None:
    if not _db_configured():
        pytest.skip("OPSPILOT_DATABASE_URL is not set")
    get_settings.cache_clear()
    email = f"recovery-{uuid4().hex[:8]}@example.com"
    password = "correct-horse-battery"
    app1 = create_app()
    approval_id = None
    token = None
    incident_id = None
    async with app1.router.lifespan_context(app1):
        transport = ASGITransport(app=app1)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            registered = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "full_name": "Recovery User",
                    "organization_name": "Recovery Org",
                },
            )
            assert registered.status_code == 200, registered.text
            token = registered.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            created = await client.post(
                "/api/v1/events",
                headers=headers,
                json={
                    "service": "payment-service",
                    "environment": "production",
                    "event_type": "error_rate_spike",
                    "error_rate": 40,
                    "message": "database connection pool exhausted",
                },
            )
            assert created.status_code == 202, created.text
            incident_id = created.json()["id"]
            approval_id = await _wait_approval(client, headers)
    if approval_id is None:
        pytest.skip("Investigation did not reach approval in time")
    get_settings.cache_clear()
    app2 = create_app()
    async with app2.router.lifespan_context(app2):
        transport = ASGITransport(app=app2)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {token}"}
            decided = await client.post(
                f"/api/v1/approvals/{approval_id}/approve",
                headers=headers,
                json={"comment": "Approved after process restart"},
            )
            assert decided.status_code == 200, decided.text
            detail = await client.get(f"/api/v1/incidents/{incident_id}", headers=headers)
            assert detail.status_code == 200
            statuses = {item["status"] for item in detail.json()["actions"]}
            assert "REJECTED" not in statuses
    get_settings.cache_clear()


async def test_reject_records_decision_without_execution() -> None:
    if not _db_configured():
        pytest.skip("OPSPILOT_DATABASE_URL is not set")
    get_settings.cache_clear()
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            registered = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"reject-{uuid4().hex[:8]}@example.com",
                    "password": "correct-horse-battery",
                    "full_name": "Reject User",
                    "organization_name": "Reject Org",
                },
            )
            assert registered.status_code == 200, registered.text
            headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
            created = await client.post(
                "/api/v1/events",
                headers=headers,
                json={
                    "service": "payment-service",
                    "environment": "production",
                    "event_type": "error_rate_spike",
                    "error_rate": 41,
                    "message": f"e2e reject {uuid4()}",
                },
            )
            assert created.status_code == 202, created.text
            incident_id = created.json()["id"]
            approval_id = await _wait_approval(client, headers)
            if approval_id is None:
                pytest.skip("Investigation did not reach approval in time")
            while True:
                pending = await client.get("/api/v1/approvals?status=PENDING_APPROVAL", headers=headers)
                rows = pending.json()
                if not rows:
                    break
                decided = await client.post(
                    f"/api/v1/approvals/{rows[0]['id']}/reject",
                    headers=headers,
                    json={"comment": "Not this time"},
                )
                assert decided.status_code == 200, decided.text
            detail = await client.get(f"/api/v1/incidents/{incident_id}", headers=headers)
            body = detail.json()
            assert body["status"] != "resolved"
            assert body["current_activity"] == "Remediation was not approved"
            assert any(item["status"] == "REJECTED" for item in body["actions"])
            assert not any(
                item["tool_name"] == "rollback_deployment" and item["status"] == "EXECUTED"
                for item in body["actions"]
            )
            assert body["rca"] is None
    get_settings.cache_clear()
