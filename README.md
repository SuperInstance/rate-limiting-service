# Rate Limiting Service

**Priority**: 8/10
**Status**: Production-Ready

## Overview

A production-ready rate limiting service implementing the token bucket algorithm with Redis backing for distributed systems. Supports both local (in-memory) and distributed (Redis-based) rate limiting with configurable strategies.

## Features

- **Token Bucket Algorithm**: Industry-standard rate limiting algorithm
- **Redis-backed Distributed Limiting**: Coordinate rate limits across multiple instances
- **Local Fallback**: Works without external dependencies
- **Multiple Strategies**: Token bucket and fixed window strategies
- **Per-Provider Limits**: Configure different limits for different providers
- **Per-User Limits**: Custom limits for specific users
- **Burst Capacity**: Allow short bursts while maintaining long-term limits
- **Automatic Cleanup**: Expired entries automatically cleaned up
- **Async/Await**: Full async/await support
- **Exponential Backoff**: Smart waiting when rate limited

## Installation

```bash
# Basic installation (local rate limiting)
pip install rate-limiting-service

# With Redis support
pip install rate-limiting-service[redis]
```

## Quick Start

### Basic Usage (Local)

```python
from rate_limiting import RateLimiter, RateLimitRule

# Create rate limiter
limiter = RateLimiter()

# Set up rules for a provider
limiter.set_provider_rule("openai", RateLimitRule(
    requests_per_minute=60,
    requests_per_hour=3000,
    requests_per_day=100000,
    burst_capacity=20
))

# Check if request is allowed
can_proceed, remaining = await limiter.check_rate_limit("openai")

if can_proceed:
    # Make the request
    pass
else:
    print(f"Rate limited. Remaining: {remaining}")
```

### With Redis (Distributed)

```python
from rate_limiting import RateLimiter, RateLimitRule

# Create rate limiter with Redis
limiter = RateLimiter(redis_url="redis://localhost:6379")
await limiter.connect()

# Use as normal
can_proceed, remaining = await limiter.check_rate_limit("openai", user_id="user123")

# Clean up
await limiter.disconnect()
```

### Wait for Capacity

```python
# Automatically wait until capacity is available
success = await limiter.wait_if_needed("openai", user_id="user123", max_wait_seconds=30)

if success:
    # Make the request
    pass
else:
    print("Timed out waiting for rate limit")
```

## Advanced Usage

### Per-User Rate Limits

```python
# Set custom limit for a specific user
limiter.set_user_rate_limit("user123", RateLimitRule(
    requests_per_minute=10,
    requests_per_hour=100,
    requests_per_day=1000,
    burst_capacity=5
))

# Check with user-specific limit
can_proceed, remaining = await limiter.check_rate_limit("openai", user_id="user123")
```

### Get Rate Limit Status

```python
status = await limiter.get_rate_limit_status("openai", user_id="user123")

print(f"Provider: {status['provider']}")
print(f"Current usage: {status['current']}")
print(f"Remaining: {status['remaining']}")
print(f"Is limited: {status['is_limited']}")
```

### Reset Rate Limits

```python
# Reset limits for a provider/user
await limiter.reset_rate_limits("openai", user_id="user123")
```

## Strategies

### Token Bucket Strategy

```python
from rate_limiting.strategies import TokenBucketStrategy, TokenBucketConfig

# Configure token bucket
config = TokenBucketConfig(
    capacity=100,  # Max tokens in bucket
    refill_rate=1.0  # Tokens per second
)

strategy = TokenBucketStrategy(config)

# Acquire tokens
if await strategy.acquire(tokens=1):
    # Proceed
    pass

# Or wait for tokens
success = await strategy.acquire_or_wait(tokens=10, max_wait=60)
```

### Fixed Window Strategy

```python
from rate_limiting.strategies import FixedWindowStrategy, FixedWindowConfig

# Configure fixed window
config = FixedWindowConfig(
    window_size_seconds=60,
    max_requests=100
)

strategy = FixedWindowStrategy(config)

# Acquire request slot
if await strategy.acquire():
    # Proceed
    pass

# Get current status
print(f"Used: {strategy.get_count()}")
print(f"Remaining: {strategy.get_remaining()}")
```

## API Reference

### RateLimiter

Main rate limiting class.

**Methods**:
- `async connect()`: Connect to Redis (if configured)
- `async disconnect()`: Disconnect from Redis
- `set_provider_rule(provider: str, rule: RateLimitRule)`: Set rule for provider
- `set_user_rate_limit(user_id: str, rule: RateLimitRule)`: Set user-specific rule
- `async check_rate_limit(provider: str, user_id: str = None) -> tuple[bool, Dict]`: Check if request allowed
- `async wait_if_needed(provider: str, user_id: str = None, max_wait_seconds: int = 60) -> bool`: Wait for capacity
- `async get_rate_limit_status(provider: str, user_id: str = None) -> Dict`: Get current status
- `async reset_rate_limits(provider: str, user_id: str = None)`: Reset limits

### RateLimitRule

Rate limiting rule configuration.

**Fields**:
- `requests_per_minute: int`: Requests per minute limit
- `requests_per_hour: int`: Requests per hour limit
- `requests_per_day: int`: Requests per day limit
- `burst_capacity: int`: Allow short bursts

## Configuration

### Without Redis (Local)

Works out of the box with no configuration needed. Rate limits are stored in memory.

### With Redis (Distributed)

```python
limiter = RateLimiter(redis_url="redis://localhost:6379")
await limiter.connect()
```

## Best Practices

1. **Use Redis for Production**: Deploy with Redis for distributed rate limiting
2. **Set Appropriate Limits**: Configure limits based on your API tier
3. **Handle Rate Limits**: Always check return values and handle rate limiting gracefully
4. **Use wait_if_needed**: For batch operations, use wait instead of polling
5. **Monitor Status**: Track rate limit status to identify issues

## Examples

### API Middleware

```python
async def rate_limit_middleware(provider, user_id):
    limiter = RateLimiter(redis_url="redis://localhost:6379")
    await limiter.connect()

    can_proceed, remaining = await limiter.check_rate_limit(provider, user_id)

    if not can_proceed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {remaining['minute']} seconds."
        )

    return True
```

### Batch Processing

```python
async def process_batch(items, provider):
    limiter = RateLimiter(redis_url="redis://localhost:6379")
    await limiter.connect()

    for item in items:
        # Wait for capacity
        success = await limiter.wait_if_needed(provider, max_wait_seconds=60)

        if not success:
            print(f"Timeout processing item {item.id}")
            continue

        # Process item
        await process_item(item)
```

## Dependencies

**Required**: None (core library)

**Optional**:
- `redis>=4.5.0` for distributed rate limiting

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please see CONTRIBUTING.md for guidelines.
