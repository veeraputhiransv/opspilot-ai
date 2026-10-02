import pytest

from app.core.errors import RateLimitError
from app.core.rate_limit import RateLimiter


@pytest.mark.asyncio
async def test_rate_limit_hook_rejects_burst() -> None:
    limiter = RateLimiter()
    await limiter.check("ingest:test", limit=2, window_seconds=60)
    await limiter.check("ingest:test", limit=2, window_seconds=60)
    with pytest.raises(RateLimitError):
        await limiter.check("ingest:test", limit=2, window_seconds=60)


@pytest.mark.asyncio
async def test_rate_limit_keys_are_independent() -> None:
    limiter = RateLimiter()
    await limiter.check("a", limit=1, window_seconds=60)
    await limiter.check("b", limit=1, window_seconds=60)
