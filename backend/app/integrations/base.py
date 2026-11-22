"""Honest Capability State Model and base integration verification contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class HonestCapabilityState(StrEnum):
    REGISTERED = "REGISTERED"
    DEFINED_NOT_INSTALLED = "DEFINED_NOT_INSTALLED"
    INSTALLED = "INSTALLED"
    AVAILABLE = "AVAILABLE"
    VERIFIED_TESTED = "VERIFIED_TESTED"


@dataclass
class IntegrationStatus:
    """Honest status report for a single cloud/external integration."""

    provider: str
    configured: bool
    capability_state: HonestCapabilityState
    live_verified: bool
    missing_env_vars: list[str] = field(default_factory=list)
    endpoint: str | None = None
    latency_ms: int | None = None
    detail: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "capability_state": self.capability_state.value,
            "live_verified": self.live_verified,
            "missing_env_vars": self.missing_env_vars,
            "endpoint": self.endpoint,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
            "checked_at": self.checked_at,
        }


def classify_http_error(status_code: int) -> str:
    if status_code in (401, 403):
        return f"PROVIDER_AUTH_ERROR (HTTP {status_code})"
    if status_code == 429:
        return "PROVIDER_RATE_LIMITED (HTTP 429)"
    if status_code >= 500:
        return f"PROVIDER_UPSTREAM_ERROR (HTTP {status_code})"
    return f"PROVIDER_HTTP_ERROR (HTTP {status_code})"
