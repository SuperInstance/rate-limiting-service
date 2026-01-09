"""
Tests for Rate Limiter
"""

import pytest
import asyncio
from rate_limiting import RateLimiter, RateLimitRule


@pytest.fixture
async def limiter():
    """Create a rate limiter instance"""
    limiter = RateLimiter(redis_url=None)  # Use local rate limiting
    await limiter.connect()
    yield limiter
    await limiter.disconnect()


def test_rate_limit_rule():
    """Test RateLimitRule creation"""
    rule = RateLimitRule(
        requests_per_minute=60,
        requests_per_hour=1000,
        requests_per_day=10000,
        burst_capacity=10
    )

    assert rule.requests_per_minute == 60
    assert rule.requests_per_hour == 1000
    assert rule.requests_per_day == 10000
    assert rule.burst_capacity == 10


def test_limiter_initialization():
    """Test rate limiter initialization"""
    limiter = RateLimiter(redis_url=None)
    assert limiter.redis_url == "redis://localhost:6379"
    assert limiter._redis is None
    assert len(limiter._local_counters) == 0


@pytest.mark.asyncio
async def test_set_provider_rule(limiter):
    """Test setting provider rate limit rule"""
    rule = RateLimitRule(
        requests_per_minute=100,
        requests_per_hour=2000,
        requests_per_day=20000
    )
    limiter.set_provider_rule("openai", rule)

    retrieved = limiter.get_rate_limit_rule("openai")
    assert retrieved.requests_per_minute == 100


@pytest.mark.asyncio
async def test_default_rate_limit(limiter):
    """Test default rate limit when no rule is set"""
    rule = limiter.get_rate_limit_rule("unknown_provider")
    assert rule.requests_per_minute == 60
    assert rule.requests_per_hour == 1000
    assert rule.requests_per_day == 10000


@pytest.mark.asyncio
async def test_check_rate_limit_under_limit(limiter):
    """Test rate limit check when under limit"""
    rule = RateLimitRule(
        requests_per_minute=10,
        requests_per_hour=100,
        requests_per_day=1000
    )
    limiter.set_provider_rule("test_provider", rule)

    allowed, remaining = await limiter.check_rate_limit("test_provider")
    assert allowed is True
    assert remaining['minute'] == 9  # 10 - 1


@pytest.mark.asyncio
async def test_check_rate_limit_exceeded(limiter):
    """Test rate limit check when limit exceeded"""
    rule = RateLimitRule(
        requests_per_minute=2,
        requests_per_hour=100,
        requests_per_day=1000
    )
    limiter.set_provider_rule("test_provider", rule)

    # First request
    allowed1, _ = await limiter.check_rate_limit("test_provider")
    assert allowed1 is True

    # Second request
    allowed2, _ = await limiter.check_rate_limit("test_provider")
    assert allowed2 is True

    # Third request should be blocked
    allowed3, remaining = await limiter.check_rate_limit("test_provider")
    assert allowed3 is False
    assert remaining['minute'] == 0


@pytest.mark.asyncio
async def test_user_specific_rate_limit(limiter):
    """Test user-specific rate limits"""
    user_rule = RateLimitRule(
        requests_per_minute=5,
        requests_per_hour=500,
        requests_per_day=5000
    )
    limiter.set_user_rate_limit("user123", user_rule)

    allowed, remaining = await limiter.check_rate_limit("default_provider", "user123")
    assert allowed is True
    assert remaining['minute'] == 4


@pytest.mark.asyncio
async def test_get_rate_limit_status(limiter):
    """Test getting rate limit status"""
    rule = RateLimitRule(
        requests_per_minute=10,
        requests_per_hour=100,
        requests_per_day=1000
    )
    limiter.set_provider_rule("test_provider", rule)

    # Make a request
    await limiter.check_rate_limit("test_provider")

    status = await limiter.get_rate_limit_status("test_provider")
    assert status['provider'] == 'test_provider'
    assert status['limits']['minute'] == 10
    assert status['current']['minute'] == 1
    assert status['remaining']['minute'] == 9


@pytest.mark.asyncio
async def test_reset_rate_limits(limiter):
    """Test resetting rate limits"""
    rule = RateLimitRule(
        requests_per_minute=10,
        requests_per_hour=100,
        requests_per_day=1000
    )
    limiter.set_provider_rule("test_provider", rule)

    # Make some requests
    await limiter.check_rate_limit("test_provider")
    await limiter.check_rate_limit("test_provider")

    # Reset
    await limiter.reset_rate_limits("test_provider")

    # Check counter is reset
    status = await limiter.get_rate_limit_status("test_provider")
    assert status['current']['minute'] == 0


@pytest.mark.asyncio
async def test_wait_if_needed(limiter):
    """Test wait_if_needed method"""
    rule = RateLimitRule(
        requests_per_minute=1,
        requests_per_hour=100,
        requests_per_day=1000
    )
    limiter.set_provider_rule("test_provider", rule)

    # First call should succeed immediately
    result = await limiter.wait_if_needed("test_provider", max_wait_seconds=1)
    assert result is True

    # Second call should wait and potentially timeout
    # Since we only wait 1 second and the limit is 1 per minute,
    # this will return False
    result = await limiter.wait_if_needed("test_provider", max_wait_seconds=1)
    assert result is False  # Timeout


@pytest.mark.asyncio
async def test_multiple_providers(limiter):
    """Test rate limiting for multiple providers independently"""
    rule1 = RateLimitRule(
        requests_per_minute=5,
        requests_per_hour=100,
        requests_per_day=1000
    )
    rule2 = RateLimitRule(
        requests_per_minute=10,
        requests_per_hour=200,
        requests_per_day=2000
    )

    limiter.set_provider_rule("provider1", rule1)
    limiter.set_provider_rule("provider2", rule2)

    # Use up provider1's limit
    for _ in range(5):
        await limiter.check_rate_limit("provider1")

    # Provider1 should be at limit
    allowed1, _ = await limiter.check_rate_limit("provider1")
    assert allowed1 is False

    # Provider2 should still have capacity
    allowed2, _ = await limiter.check_rate_limit("provider2")
    assert allowed2 is True
