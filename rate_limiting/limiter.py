"""
Rate limiting system for API providers
"""

import time
import asyncio
from typing import Dict, Optional
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


@dataclass
class RateLimitRule:
    """Rate limiting rule for a provider"""
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    burst_capacity: int = 10  # Allow short bursts


class RateLimiter:
    """Rate limiter for API providers"""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or "redis://localhost:6379"
        self._redis = None

        # Local rate limiting for fast checks
        self._local_counters: Dict[str, Dict[str, deque]] = defaultdict(lambda: {
            'minute': deque(),
            'hour': deque(),
            'day': deque()
        })

        # Rate limit rules for each provider
        self._rules: Dict[str, RateLimitRule] = {}

        # User-specific rate limiting
        self._user_limits: Dict[str, RateLimitRule] = {}

    async def connect(self) -> None:
        """Connect to Redis"""
        if REDIS_AVAILABLE and self.redis_url:
            try:
                self._redis = redis.from_url(self.redis_url, decode_responses=True)
                await self._redis.ping()
            except Exception:
                self._redis = None

    async def disconnect(self) -> None:
        """Disconnect from Redis"""
        if self._redis:
            await self._redis.close()

    def set_provider_rule(self, provider: str, rule: RateLimitRule) -> None:
        """Set rate limit rule for a provider"""
        self._rules[provider] = rule

    def set_user_rate_limit(self, user_id: str, rule: RateLimitRule) -> None:
        """Set custom rate limit for a user"""
        self._user_limits[user_id] = rule

    def get_rate_limit_rule(self, provider: str, user_id: Optional[str] = None) -> RateLimitRule:
        """Get rate limit rule for provider/user"""
        if user_id and user_id in self._user_limits:
            return self._user_limits[user_id]

        if provider in self._rules:
            return self._rules[provider]

        # Default rule if none set
        return RateLimitRule(
            requests_per_minute=60,
            requests_per_hour=1000,
            requests_per_day=10000,
            burst_capacity=10
        )

    async def check_rate_limit(
        self,
        provider: str,
        user_id: Optional[str] = None
    ) -> tuple[bool, Dict[str, int]]:
        """Check if request is allowed under rate limits"""
        rule = self.get_rate_limit_rule(provider, user_id)

        # Use Redis for distributed rate limiting
        if self._redis:
            return await self._check_redis_rate_limit(provider, user_id, rule)
        else:
            return self._check_local_rate_limit(provider, user_id, rule)

    async def _check_redis_rate_limit(
        self,
        provider: str,
        user_id: Optional[str],
        rule: RateLimitRule
    ) -> tuple[bool, Dict[str, int]]:
        """Check rate limits using Redis"""
        now = int(time.time())
        minute_key = f"rate_limit:{provider}:{user_id or 'global'}:minute"
        hour_key = f"rate_limit:{provider}:{user_id or 'global'}:hour"
        day_key = f"rate_limit:{provider}:{user_id or 'global'}:day"

        pipe = self._redis.pipeline()

        # Get current counts
        pipe.zremrangebyscore(minute_key, 0, now - 60)
        pipe.zcard(minute_key)
        pipe.zremrangebyscore(hour_key, 0, now - 3600)
        pipe.zcard(hour_key)
        pipe.zremrangebyscore(day_key, 0, now - 86400)
        pipe.zcard(day_key)

        results = await pipe.execute()

        minute_count = results[1]
        hour_count = results[3]
        day_count = results[5]

        # Check limits
        can_proceed = (
            minute_count < rule.requests_per_minute and
            hour_count < rule.requests_per_hour and
            day_count < rule.requests_per_day
        )

        remaining = {
            'minute': max(0, rule.requests_per_minute - minute_count),
            'hour': max(0, rule.requests_per_hour - hour_count),
            'day': max(0, rule.requests_per_day - day_count)
        }

        if can_proceed:
            # Add current request
            pipe = self._redis.pipeline()
            pipe.zadd(minute_key, {str(now): now})
            pipe.expire(minute_key, 120)  # 2 minutes TTL
            pipe.zadd(hour_key, {str(now): now})
            pipe.expire(hour_key, 7200)  # 2 hours TTL
            pipe.zadd(day_key, {str(now): now})
            pipe.expire(day_key, 172800)  # 2 days TTL
            await pipe.execute()

        return can_proceed, remaining

    def _check_local_rate_limit(
        self,
        provider: str,
        user_id: Optional[str],
        rule: RateLimitRule
    ) -> tuple[bool, Dict[str, int]]:
        """Check rate limits using local counters"""
        now = time.time()
        key = f"{provider}:{user_id or 'global'}"
        counters = self._local_counters[key]

        # Clean old entries
        while counters['minute'] and now - counters['minute'][0] > 60:
            counters['minute'].popleft()
        while counters['hour'] and now - counters['hour'][0] > 3600:
            counters['hour'].popleft()
        while counters['day'] and now - counters['day'][0] > 86400:
            counters['day'].popleft()

        # Check limits
        can_proceed = (
            len(counters['minute']) < rule.requests_per_minute and
            len(counters['hour']) < rule.requests_per_hour and
            len(counters['day']) < rule.requests_per_day
        )

        remaining = {
            'minute': max(0, rule.requests_per_minute - len(counters['minute'])),
            'hour': max(0, rule.requests_per_hour - len(counters['hour'])),
            'day': max(0, rule.requests_per_day - len(counters['day']))
        }

        if can_proceed:
            # Add current request
            timestamp = now
            counters['minute'].append(timestamp)
            counters['hour'].append(timestamp)
            counters['day'].append(timestamp)

        return can_proceed, remaining

    async def wait_if_needed(
        self,
        provider: str,
        user_id: Optional[str] = None,
        max_wait_seconds: int = 60
    ) -> bool:
        """Wait if rate limited, return False if max wait exceeded"""
        start_time = time.time()

        while time.time() - start_time < max_wait_seconds:
            can_proceed, _ = await self.check_rate_limit(provider, user_id)
            if can_proceed:
                return True

            # Exponential backoff
            wait_time = min(1.0, (time.time() - start_time) * 0.1)
            await asyncio.sleep(wait_time)

        return False

    async def get_rate_limit_status(
        self,
        provider: str,
        user_id: Optional[str] = None
    ) -> Dict[str, any]:
        """Get current rate limit status"""
        rule = self.get_rate_limit_rule(provider, user_id)

        if self._redis:
            now = int(time.time())
            minute_key = f"rate_limit:{provider}:{user_id or 'global'}:minute"
            hour_key = f"rate_limit:{provider}:{user_id or 'global'}:hour"
            day_key = f"rate_limit:{provider}:{user_id or 'global'}:day"

            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(minute_key, 0, now - 60)
            pipe.zcard(minute_key)
            pipe.zremrangebyscore(hour_key, 0, now - 3600)
            pipe.zcard(hour_key)
            pipe.zremrangebyscore(day_key, 0, now - 86400)
            pipe.zcard(day_key)

            results = await pipe.execute()
            minute_count, hour_count, day_count = results[1], results[3], results[5]
        else:
            key = f"{provider}:{user_id or 'global'}"
            counters = self._local_counters[key]
            now = time.time()

            # Clean old entries
            while counters['minute'] and now - counters['minute'][0] > 60:
                counters['minute'].popleft()
            while counters['hour'] and now - counters['hour'][0] > 3600:
                counters['hour'].popleft()
            while counters['day'] and now - counters['day'][0] > 86400:
                counters['day'].popleft()

            minute_count = len(counters['minute'])
            hour_count = len(counters['hour'])
            day_count = len(counters['day'])

        return {
            'provider': provider,
            'user_id': user_id,
            'limits': {
                'minute': rule.requests_per_minute,
                'hour': rule.requests_per_hour,
                'day': rule.requests_per_day
            },
            'current': {
                'minute': minute_count,
                'hour': hour_count,
                'day': day_count
            },
            'remaining': {
                'minute': max(0, rule.requests_per_minute - minute_count),
                'hour': max(0, rule.requests_per_hour - hour_count),
                'day': max(0, rule.requests_per_day - day_count)
            },
            'is_limited': (
                minute_count >= rule.requests_per_minute or
                hour_count >= rule.requests_per_hour or
                day_count >= rule.requests_per_day
            )
        }

    async def reset_rate_limits(
        self,
        provider: str,
        user_id: Optional[str] = None
    ) -> None:
        """Reset rate limits for provider/user"""
        if self._redis:
            patterns = [
                f"rate_limit:{provider}:{user_id or 'global'}:*"
            ]
            for pattern in patterns:
                keys = await self._redis.keys(pattern)
                if keys:
                    await self._redis.delete(*keys)
        else:
            key = f"{provider}:{user_id or 'global'}"
            self._local_counters[key] = {
                'minute': deque(),
                'hour': deque(),
                'day': deque()
            }
