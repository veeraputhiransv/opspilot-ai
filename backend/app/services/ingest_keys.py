"""Idempotent event ingest.

Retries must not open a second investigation. The client should send
`idempotency_key`. If it does not, OpsPilot derives one from the workspace and
the canonical event fields. The unique key is `(workspace_id, idempotency_key)`.
"""

from hashlib import sha256
from uuid import UUID

from app.schemas.api import EventIn


def ingest_idempotency_key(workspace_id: UUID, event: EventIn) -> str:
    if event.idempotency_key:
        return event.idempotency_key.strip()
    stamp = event.timestamp.isoformat() if event.timestamp else ""
    material = "|".join(
        [
            str(workspace_id),
            event.service,
            event.environment,
            event.event_type,
            f"{event.error_rate:.6f}",
            event.message,
            stamp,
        ]
    )
    return sha256(material.encode("utf-8")).hexdigest()
