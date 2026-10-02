"""Redis sliding-window limiter with an in-process fallback."""

import time
from collections import defaultdict
from typing import Any

from app.core.errors import RateLimitError


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._redis: Any | None = None

    def bind_redis(self, redis: Any | None) -> None:
        self._redis = redis

    async def check(self, key: str, *, limit: int, window_seconds: float = 60) -> None:
        retry = int(window_seconds)
        if self._redis is not None:
            try:
                namespaced = f"rl:{key}"
                count = await self._redis.incr(namespaced)
                if count == 1:
                    await self._redis.expire(namespaced, retry)
                if count > limit:
                    raise RateLimitError(
                        "Rate limit exceeded. Try again shortly.", retry_after=retry
                    )
                return
            except RateLimitError:
                raise
            except Exception:
                pass
        now = time.monotonic()
        recent = [stamp for stamp in self._hits[key] if now - stamp < window_seconds]
        if len(recent) >= limit:
            raise RateLimitError("Rate limit exceeded. Try again shortly.", retry_after=retry)
        recent.append(now)
        self._hits[key] = recent
