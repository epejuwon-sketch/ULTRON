"""Rate Limiting for ULTRON OS 2026: Shared Production Upstash Redis REST & Local Sliding Window."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

import httpx

from app.core.config import Settings


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding-window rate limiter (60-second window) for dev/single-node."""

    backend_name = "in_memory"

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


class SharedRedisRestRateLimiter:
    """Shared multi-instance fixed-window rate limiter backed by Redis REST (e.g. Upstash) for serverless Vercel."""

    backend_name = "shared_redis_rest"

    def __init__(
        self,
        *,
        rest_url: str,
        rest_token: str,
        limit_per_minute: int = 180,
        window_seconds: int = 60,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.rest_url = rest_url.rstrip("/")
        self.rest_token = rest_token
        self.limit = max(1, int(limit_per_minute))
        self.window_seconds = max(1, int(window_seconds))
        self._client = http_client
        self._fallback = SlidingWindowRateLimiter(limit_per_minute=self.limit, window_seconds=float(self.window_seconds))

    def check(self, key: str) -> tuple[bool, int, int]:
        bucket = int(time.time()) // self.window_seconds
        redis_key = f"ultron:rl:{key}:{bucket}"
        pipeline = [
            ["INCR", redis_key],
            ["EXPIRE", redis_key, self.window_seconds + 5],
        ]
        try:
            headers = {"Authorization": f"Bearer {self.rest_token}", "Content-Type": "application/json"}
            if self._client is not None:
                resp = self._client.post(f"{self.rest_url}/pipeline", headers=headers, json=pipeline)
            else:
                with httpx.Client(timeout=2.0) as client:
                    resp = client.post(f"{self.rest_url}/pipeline", headers=headers, json=pipeline)
            resp.raise_for_status()
            data = resp.json()
            count = int(data[0]["result"])
            if count > self.limit:
                retry_after = max(1, self.window_seconds - (int(time.time()) % self.window_seconds))
                return False, 0, retry_after
            return True, max(0, self.limit - count), 0
        except Exception:
            # Fail safely to local sliding window if Redis has a transient blip
            return self._fallback.check(key)

    def reset(self) -> None:
        self._fallback.reset()


def build_rate_limiter(settings: Settings) -> SlidingWindowRateLimiter | SharedRedisRestRateLimiter:
    """Select shared Redis REST rate limiter when configured; fall back to local sliding window."""
    if (
        settings.redis_rest_url.strip()
        and settings.redis_rest_token
        and settings.redis_rest_token.get_secret_value().strip()
    ):
        return SharedRedisRestRateLimiter(
            rest_url=settings.redis_rest_url.strip(),
            rest_token=settings.redis_rest_token.get_secret_value().strip(),
            limit_per_minute=settings.rate_limit_requests_per_minute,
        )
    return SlidingWindowRateLimiter(limit_per_minute=settings.rate_limit_requests_per_minute)
