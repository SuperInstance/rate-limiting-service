"""
Token bucket rate limiting strategy
"""

import time
import asyncio
from typing import Optional
from dataclasses import dataclass


@dataclass
class TokenBucketConfig:
    """Token bucket configuration"""
    capacity: int  # Maximum tokens in bucket
    refill_rate: float  # Tokens per second


class TokenBucketStrategy:
    """Token bucket rate limiting strategy"""

    def __init__(self, config: TokenBucketConfig):
        self.config = config
        self._tokens = float(config.capacity)
        self._last_refill = time.time()

    def _refill_tokens(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self._last_refill

        # Calculate tokens to add
        tokens_to_add = elapsed * self.config.refill_rate

        # Update tokens (cap at capacity)
        self._tokens = min(self.config.capacity, self._tokens + tokens_to_add)
        self._last_refill = now

    async def acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens"""
        self._refill_tokens()

        if self._tokens >= tokens:
            self._tokens -= tokens
            return True

        return False

    async def acquire_or_wait(self, tokens: int = 1, max_wait: float = 60.0) -> bool:
        """Acquire tokens, waiting if necessary"""
        start_time = time.time()

        while time.time() - start_time < max_wait:
            if await self.acquire(tokens):
                return True

            # Calculate wait time needed for refill
            tokens_needed = tokens - self._tokens
            wait_time = tokens_needed / self.config.refill_rate

            # Wait a bit
            await asyncio.sleep(min(wait_time, 0.1))

        return False

    def available_tokens(self) -> int:
        """Get number of available tokens"""
        self._refill_tokens()
        return int(self._tokens)

    def reset(self):
        """Reset the token bucket"""
        self._tokens = float(self.config.capacity)
        self._last_refill = time.time()
