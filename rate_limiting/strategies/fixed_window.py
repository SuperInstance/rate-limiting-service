"""
Fixed window rate limiting strategy
"""

import time
from typing import Dict, Tuple
from collections import deque
from dataclasses import dataclass


@dataclass
class FixedWindowConfig:
    """Fixed window configuration"""
    window_size_seconds: int
    max_requests: int


class FixedWindowStrategy:
    """Fixed window rate limiting strategy"""

    def __init__(self, config: FixedWindowConfig):
        self.config = config
        self._windows: Dict[int, deque] = {}

    def _get_window_key(self) -> int:
        """Get current window key"""
        return int(time.time() // self.config.window_size_seconds)

    def _cleanup_old_windows(self):
        """Clean up old windows"""
        current_window = self._get_window_key()
        old_windows = [
            key for key in self._windows.keys()
            if key < current_window - 1
        ]

        for key in old_windows:
            del self._windows[key]

    async def acquire(self) -> bool:
        """Try to acquire a request slot"""
        current_window = self._get_window_key()

        # Clean up old windows periodically
        if len(self._windows) > 100:
            self._cleanup_old_windows()

        # Get or create window
        if current_window not in self._windows:
            self._windows[current_window] = deque()

        window = self._windows[current_window]

        # Check if we have capacity
        if len(window) < self.config.max_requests:
            window.append(time.time())
            return True

        return False

    def get_count(self) -> int:
        """Get current window request count"""
        current_window = self._get_window_key()
        window = self._windows.get(current_window, deque())
        return len(window)

    def get_remaining(self) -> int:
        """Get remaining requests in current window"""
        return max(0, self.config.max_requests - self.get_count())

    def reset(self):
        """Reset all windows"""
        self._windows.clear()
