import pytest

from app.services.rate_limiter import MemoryRateLimiter


@pytest.mark.asyncio
async def test_allows_within_limit():
    limiter = MemoryRateLimiter()
    for i in range(3):
        verdict = await limiter.hit("user:1", limit=3, window_sec=60)
        assert verdict.allowed is True
        assert verdict.remaining == 2 - i


@pytest.mark.asyncio
async def test_blocks_over_limit_and_reports_retry_after():
    limiter = MemoryRateLimiter()
    for _ in range(2):
        await limiter.hit("user:1", limit=2, window_sec=60)

    verdict = await limiter.hit("user:1", limit=2, window_sec=60)
    assert verdict.allowed is False
    assert verdict.remaining == 0
    assert 0 < verdict.retry_after_sec <= 61


@pytest.mark.asyncio
async def test_limits_are_per_user():
    limiter = MemoryRateLimiter()
    await limiter.hit("user:1", limit=1, window_sec=60)
    assert (await limiter.hit("user:1", limit=1, window_sec=60)).allowed is False
    assert (await limiter.hit("user:2", limit=1, window_sec=60)).allowed is True


@pytest.mark.asyncio
async def test_window_expiry_releases_quota():
    limiter = MemoryRateLimiter()
    await limiter.hit("user:1", limit=1, window_sec=0)
    assert (await limiter.hit("user:1", limit=1, window_sec=0)).allowed is True
