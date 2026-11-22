"""In-memory sliding-window rate limiter for FastAPI requests."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Thread-safe per-key sliding-window rate limiter (60-second window)."""

    def __init__(self, limit_per_minute: int = 180, window_seconds: float = 60.0) -> None:
        self.limit = max(1, int(limit_per_minute))
        self.window_seconds = float(window_seconds)
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int, int]:
        """Record a hit and return `(allowed, remaining, retry_after_seconds)`."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            q = self._buckets[key]
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (now - q[0])))
                return False, 0, retry_after
            q.append(now)
            remaining = max(0, self.limit - len(q))
            return True, remaining, 0

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()
