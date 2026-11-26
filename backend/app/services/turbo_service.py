"""TURBO — Performance Optimization, Bounded TTL Cache & Real Benchmark Suite.

Never fabricates speedup percentages — measures real latencies across DB probes,
NEON routing, local semantic embeddings, AES-256-GCM encryption, and secret interception.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.secret_interceptor import intercept_and_redact_secrets
from app.core.security import decrypt_vault_secret, encrypt_vault_secret
from app.services.memory_service import compute_local_embedding
from app.services.neon_router import route_objective


class TurboTTLCache:
    """Thread-safe bounded in-memory TTL cache with real hit/miss telemetry."""

    def __init__(self, max_entries: int = 256, default_ttl_seconds: float = 30.0) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, Any]] = {}
        self.max_entries = max_entries
        self.default_ttl = default_ttl_seconds
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            expires_at, val = entry
            if now >= expires_at:
                self._store.pop(key, None)
                self.misses += 1
                return None
            self.hits += 1
            return val

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        now = time.monotonic()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        with self._lock:
            if len(self._store) >= self.max_entries:
                # Evict earliest expiring key
                oldest_key = min(self._store.items(), key=lambda kv: kv[1][0])[0]
                self._store.pop(oldest_key, None)
            self._store[key] = (now + ttl, value)

    def clear(self) -> int:
        with self._lock:
            n = len(self._store)
            self._store.clear()
            return n

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            hit_rate = round((self.hits / total) * 100.0, 2) if total else 0.0
            return {
                "entries": len(self._store),
                "max_entries": self.max_entries,
                "default_ttl_seconds": self.default_ttl,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate_pct": hit_rate,
            }


turbo_cache = TurboTTLCache()


def run_real_benchmarks(db: Session, settings: Settings, iterations: int = 25) -> dict[str, Any]:
    """Execute real micro-benchmarks and report actual measured latencies in milliseconds."""
    iters = max(5, min(100, iterations))

    # 1. Database SELECT 1 latency
    t0 = time.perf_counter()
    for _ in range(iters):
        db.execute(text("SELECT 1"))
    db_ms = ((time.perf_counter() - t0) * 1000.0) / iters

    # 2. NEON objective routing latency
    t0 = time.perf_counter()
    for _ in range(iters):
        route_objective("Review our Supabase PostgreSQL schema and index strategy", settings=settings)
    neon_ms = ((time.perf_counter() - t0) * 1000.0) / iters

    # 3. Local semantic embedding latency
    t0 = time.perf_counter()
    for _ in range(iters):
        compute_local_embedding("ULTRON OS 2026 multi-agent intelligence architecture with AEGIS security")
    embed_ms = ((time.perf_counter() - t0) * 1000.0) / iters

    # 4. AES-256-GCM encrypt + decrypt roundtrip
    master_key = settings.vault_master_key.get_secret_value()
    t0 = time.perf_counter()
    for _ in range(iters):
        ct, nonce = encrypt_vault_secret("benchmark-payload-value-2026", master_secret=master_key, aad="turbo:bench")
        decrypt_vault_secret(ct, nonce, master_secret=master_key, aad="turbo:bench")
    crypto_ms = ((time.perf_counter() - t0) * 1000.0) / iters

    # 5. VAULT secret interception regex/Luhn scan
    t0 = time.perf_counter()
    for _ in range(iters):
        intercept_and_redact_secrets("Analyze quarterly report with no secrets included.", auto_vault=False)
    intercept_ms = ((time.perf_counter() - t0) * 1000.0) / iters

    return {
        "iterations": iters,
        "measured": True,
        "benchmarks_avg_ms": {
            "db_select_1_ms": round(db_ms, 4),
            "neon_route_objective_ms": round(neon_ms, 4),
            "local_embedding_64d_ms": round(embed_ms, 4),
            "vault_aes256gcm_roundtrip_ms": round(crypto_ms, 4),
            "secret_interception_scan_ms": round(intercept_ms, 4),
        },
        "cache_stats": turbo_cache.stats(),
    }
