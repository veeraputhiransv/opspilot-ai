"""Short-lived SSE tickets. They are not JWTs and cannot call REST APIs."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any
from uuid import UUID

from app.core.errors import ForbiddenError, UnauthorizedError
from app.identity.context import AuthContext
from app.models.base import utcnow


class StreamTicketService:
    def __init__(self, redis: Any | None, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._local: dict[str, dict] = {}

    async def issue(
        self, auth: AuthContext, incident_id: UUID | None = None
    ) -> dict:
        raw = token_urlsafe(32)
        digest = sha256(raw.encode("utf-8")).hexdigest()
        expires = utcnow() + timedelta(seconds=self._ttl)
        record = {
            "workspace_id": str(auth.workspace_id),
            "user_id": str(auth.user_id) if auth.user_id else None,
            "incident_id": str(incident_id) if incident_id else None,
            "expires_at": expires.isoformat(),
            "uses": 0,
            "max_uses": 8,
        }
        await self._store(digest, record)
        return {"ticket": raw, "expires_at": expires.isoformat()}

    async def consume(self, raw: str, *, incident_id: UUID | None) -> dict:
        if not raw or len(raw) < 16:
            raise UnauthorizedError("Stream ticket is invalid.")
        digest = sha256(raw.encode("utf-8")).hexdigest()
        record = await self._load(digest)
        if record is None:
            raise UnauthorizedError("Stream ticket is invalid or expired.")
        expires = datetime.fromisoformat(record["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < datetime.now(UTC):
            await self._delete(digest)
            raise UnauthorizedError("Stream ticket is expired.")
        uses = int(record.get("uses") or 0)
        if uses >= int(record.get("max_uses") or 8):
            raise UnauthorizedError("Stream ticket cannot be reused.")
        scoped = record.get("incident_id")
        if scoped and incident_id and scoped != str(incident_id):
            raise ForbiddenError("Stream ticket is not valid for this incident.")
        record["uses"] = uses + 1
        await self._store(digest, record)
        return record

    async def _store(self, digest: str, record: dict) -> None:
        payload = json.dumps(record)
        if self._redis is not None:
            try:
                await self._redis.set(f"stream_ticket:{digest}", payload, ex=self._ttl)
                return
            except Exception:
                pass
        self._local[digest] = record

    async def _load(self, digest: str) -> dict | None:
        if self._redis is not None:
            try:
                raw = await self._redis.get(f"stream_ticket:{digest}")
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        return self._local.get(digest)

    async def _delete(self, digest: str) -> None:
        self._local.pop(digest, None)
        if self._redis is not None:
            try:
                await self._redis.delete(f"stream_ticket:{digest}")
            except Exception:
                return
