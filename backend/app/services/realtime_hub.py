"""Tenant-scoped WebSocket real-time event hub and lightweight runtime request metrics tracker."""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


class RealtimeEventHub:
    """Manages authenticated tenant-scoped WebSocket connections for live backend events."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, tenant_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[tenant_id].add(websocket)

    async def disconnect(self, tenant_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[tenant_id].discard(websocket)
            if not self._connections[tenant_id]:
                self._connections.pop(tenant_id, None)

    async def broadcast_tenant(self, tenant_id: str, event_type: str, payload: dict[str, Any]) -> int:
        message = {
            "event_type": event_type,
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        async with self._lock:
            targets = list(self._connections.get(tenant_id, set()))

        delivered = 0
        stale: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(message)
                delivered += 1
            except Exception:
                stale.append(ws)
        for ws in stale:
            await self.disconnect(tenant_id, ws)
        return delivered

    def publish_sync(self, tenant_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """Best-effort publish from synchronous service code when an event loop is running."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast_tenant(tenant_id, event_type, payload))
        except RuntimeError:
            pass

    def connection_count(self) -> int:
        return sum(len(s) for s in self._connections.values())


class RequestMetricsTracker:
    """Thread-safe HTTP request metrics collector with Prometheus exposition support."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total_requests = 0
        self.total_errors = 0
        self.total_latency_ms = 0
        self.by_status: dict[int, int] = defaultdict(int)
        self.by_path: dict[str, int] = defaultdict(int)

    def record(self, path: str, status_code: int, latency_ms: int) -> None:
        with self._lock:
            self.total_requests += 1
            if status_code >= 400:
                self.total_errors += 1
            self.total_latency_ms += max(0, int(latency_ms))
            self.by_status[status_code] += 1
            self.by_path[path] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            avg = round(self.total_latency_ms / self.total_requests, 2) if self.total_requests else 0.0
            return {
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
                "avg_latency_ms": avg,
                "status_counts": dict(self.by_status),
                "top_paths": sorted(self.by_path.items(), key=lambda kv: kv[1], reverse=True)[:15],
            }

    def prometheus_text(self, *, active_ws: int = 0) -> str:
        snap = self.snapshot()
        lines = [
            "# HELP ultron_http_requests_total Total HTTP requests handled by ULTRON OS 2026",
            "# TYPE ultron_http_requests_total counter",
            f"ultron_http_requests_total {snap['total_requests']}",
            "# HELP ultron_http_errors_total Total HTTP 4xx/5xx responses",
            "# TYPE ultron_http_errors_total counter",
            f"ultron_http_errors_total {snap['total_errors']}",
            "# HELP ultron_http_avg_latency_ms Average HTTP request latency in milliseconds",
            "# TYPE ultron_http_avg_latency_ms gauge",
            f"ultron_http_avg_latency_ms {snap['avg_latency_ms']}",
            "# HELP ultron_websocket_connections Active tenant WebSocket connections",
            "# TYPE ultron_websocket_connections gauge",
            f"ultron_websocket_connections {active_ws}",
        ]
        return "\n".join(lines) + "\n"


realtime_hub = RealtimeEventHub()
metrics_tracker = RequestMetricsTracker()
