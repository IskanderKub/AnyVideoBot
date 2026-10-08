"""Rate limiting with shared state in Redis (or an in-memory fallback).

The state is deliberately kept out of process memory: with several workers the
limit must be shared, which the horizontal scaling requirement calls for.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Protocol

from loguru import logger

from app.config import settings


@dataclass(slots=True)
class RateLimitVerdict:
    allowed: bool
    remaining: int
    retry_after_sec: int


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_sec: int) -> RateLimitVerdict: ...

    async def close(self) -> None: ...


class MemoryRateLimiter:
    """Sliding window in process memory. Fine for a single worker / local dev."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def hit(self, key: str, limit: int, window_sec: int) -> RateLimitVerdict:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] >= window_sec:
            bucket.popleft()

        if len(bucket) >= limit:
            retry_after = int(window_sec - (now - bucket[0])) + 1
            return RateLimitVerdict(False, 0, max(retry_after, 1))

        bucket.append(now)
        return RateLimitVerdict(True, limit - len(bucket), 0)

    async def close(self) -> None:
        self._hits.clear()


class RedisRateLimiter:
    """Fixed window on INCR+EXPIRE - atomic and cheap."""

    def __init__(self, url: str) -> None:
        from redis.asyncio import from_url

        self._redis = from_url(url, encoding="utf-8", decode_responses=True)

    async def hit(self, key: str, limit: int, window_sec: int) -> RateLimitVerdict:
        redis_key = f"ratelimit:{key}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.ttl(redis_key)
            count, ttl = await pipe.execute()

        if ttl is None or ttl < 0:
            await self._redis.expire(redis_key, window_sec)
            ttl = window_sec

        if count > limit:
            return RateLimitVerdict(False, 0, max(int(ttl), 1))
        return RateLimitVerdict(True, limit - int(count), 0)

    async def close(self) -> None:
        await self._redis.aclose()


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        if settings.redis_url:
            _limiter = RedisRateLimiter(settings.redis_url)
            logger.info("Rate-limiter: Redis")
        else:
            _limiter = MemoryRateLimiter()
            logger.warning(
                "Rate-limiter: in-memory (REDIS_URL не задан) — "
                "лимит не будет общим между воркерами"
            )
    return _limiter


async def close_rate_limiter() -> None:
    global _limiter
    if _limiter is not None:
        await _limiter.close()
        _limiter = None
