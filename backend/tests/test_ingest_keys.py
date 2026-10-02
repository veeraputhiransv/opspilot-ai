from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.api import EventIn
from app.services.ingest_keys import ingest_idempotency_key


def _event(**overrides) -> EventIn:
    payload = {
        "service": "payment-service",
        "environment": "production",
        "event_type": "error_rate_spike",
        "error_rate": 18.5,
        "message": "checkout latency exceeded SLO",
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
    }
    payload.update(overrides)
    return EventIn.model_validate(payload)


def test_explicit_idempotency_key_is_workspace_local() -> None:
    workspace = uuid4()
    event = _event(idempotency_key="alert-12345678")
    assert ingest_idempotency_key(workspace, event) == "alert-12345678"


def test_derived_key_is_stable_for_retries() -> None:
    workspace = uuid4()
    event = _event()
    first = ingest_idempotency_key(workspace, event)
    second = ingest_idempotency_key(workspace, event)
    assert first == second
    assert len(first) == 64


def test_derived_key_changes_across_workspaces() -> None:
    event = _event()
    left = ingest_idempotency_key(uuid4(), event)
    right = ingest_idempotency_key(uuid4(), event)
    assert left != right
