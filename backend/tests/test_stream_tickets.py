from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.errors import ForbiddenError, UnauthorizedError
from app.identity.context import AuthContext
from app.services.stream_tickets import StreamTicketService


def _auth(workspace_id=None):
    return AuthContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        roles=("operator",),
        actor_label="tester@example.com",
        via="jwt",
    )


@pytest.mark.asyncio
async def test_valid_ticket_and_reconnect() -> None:
    service = StreamTicketService(None, ttl_seconds=90)
    auth = _auth()
    issued = await service.issue(auth)
    first = await service.consume(issued["ticket"], incident_id=None)
    second = await service.consume(issued["ticket"], incident_id=None)
    assert first["workspace_id"] == str(auth.workspace_id)
    assert second["uses"] == 2


@pytest.mark.asyncio
async def test_malformed_ticket() -> None:
    service = StreamTicketService(None, ttl_seconds=90)
    with pytest.raises(UnauthorizedError):
        await service.consume("short", incident_id=None)


@pytest.mark.asyncio
async def test_expired_ticket() -> None:
    service = StreamTicketService(None, ttl_seconds=90)
    auth = _auth()
    issued = await service.issue(auth)
    digest_record = await service.consume(issued["ticket"], incident_id=None)
    from hashlib import sha256

    digest = sha256(issued["ticket"].encode("utf-8")).hexdigest()
    digest_record["expires_at"] = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    service._local[digest] = digest_record
    with pytest.raises(UnauthorizedError):
        await service.consume(issued["ticket"], incident_id=None)


@pytest.mark.asyncio
async def test_ticket_use_limit() -> None:
    service = StreamTicketService(None, ttl_seconds=90)
    auth = _auth()
    issued = await service.issue(auth)
    from hashlib import sha256

    digest = sha256(issued["ticket"].encode("utf-8")).hexdigest()
    record = service._local[digest]
    record["uses"] = 8
    with pytest.raises(UnauthorizedError):
        await service.consume(issued["ticket"], incident_id=None)


@pytest.mark.asyncio
async def test_ticket_wrong_incident() -> None:
    service = StreamTicketService(None, ttl_seconds=90)
    auth = _auth()
    issued = await service.issue(auth, incident_id=uuid4())
    with pytest.raises(ForbiddenError):
        await service.consume(issued["ticket"], incident_id=uuid4())
