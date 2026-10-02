"""Redis pub/sub with an in-process fallback.

The stream is an invalidation signal. Clients refetch the incident from Postgres.
"""

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("opspilot.bus")
CHANNEL = "opspilot.events"


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._redis_ok = False
        self._pub: Any = None
        self._sub: Any = None
        self._listener: asyncio.Task | None = None

    async def connect(self, redis_url: str) -> None:
        try:
            from redis.asyncio import Redis

            self._pub = Redis.from_url(redis_url, decode_responses=True)
            await self._pub.ping()
            self._sub = Redis.from_url(redis_url, decode_responses=True)
            pubsub = self._sub.pubsub()
            await pubsub.subscribe(CHANNEL)
            self._listener = asyncio.create_task(self._listen(pubsub))
            self._redis_ok = True
            logger.info("redis_bus_connected")
        except Exception:
            self._redis_ok = False
            logger.warning("redis_unavailable_using_local_bus")

    async def close(self) -> None:
        if self._listener:
            self._listener.cancel()
            try:
                await self._listener
            except asyncio.CancelledError:
                pass
        if self._pub is not None:
            await self._pub.aclose()
        if self._sub is not None:
            await self._sub.aclose()

    def subscribe(
        self, workspace_id: str, incident_id: str | None
    ) -> tuple[asyncio.Queue, Callable[[], None]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        key = f"{workspace_id}:{incident_id or '*'}"
        self._subs[key].add(queue)

        def unsubscribe() -> None:
            self._subs[key].discard(queue)

        return queue, unsubscribe

    async def publish(self, event: dict) -> None:
        if self._redis_ok and self._pub is not None:
            try:
                await self._pub.publish(CHANNEL, json.dumps(event))
            except Exception:
                logger.warning("redis_publish_failed")
                self._redis_ok = False
        self._fanout(event)

    async def _listen(self, pubsub: Any) -> None:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            raw = message.get("data")
            if not isinstance(raw, str):
                continue
            try:
                self._fanout(json.loads(raw))
            except json.JSONDecodeError:
                logger.warning("dropped_invalid_bus_payload")

    def _fanout(self, event: dict) -> None:
        workspace_id = str(event.get("workspace_id") or "")
        incident_id = str(event.get("incident_id") or "")
        keys = []
        if workspace_id:
            keys.append(f"{workspace_id}:*")
            if incident_id:
                keys.append(f"{workspace_id}:{incident_id}")
        targets: list[asyncio.Queue] = []
        for key in keys:
            targets.extend(self._subs.get(key, set()))
        for queue in targets:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    continue
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                continue
