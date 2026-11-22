"""Vercel API integration client, webhook verification, and live health check."""

from __future__ import annotations

import hashlib
import hmac
import time

import httpx

from app.core.config import Settings
from app.integrations.base import HonestCapabilityState, IntegrationStatus, classify_http_error


class VercelClient:
    """Vercel deployment/project inspection and webhook verification client."""

    BASE_URL = "https://api.vercel.com"

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = http_client

    @property
    def _token(self) -> str:
        if self._settings.vercel_token:
            return self._settings.vercel_token.get_secret_value().strip()
        return ""

    def missing_env_vars(self) -> list[str]:
        return [] if self._token else ["VERCEL_TOKEN"]

    def is_configured(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def verify_webhook_signature(self, raw_body: bytes, signature_header: str) -> bool:
        """Verify Vercel `x-vercel-signature` (HMAC-SHA1) header in constant time."""
        if not self._settings.vercel_webhook_secret:
            return False
        secret = self._settings.vercel_webhook_secret.get_secret_value().encode("utf-8")
        expected = hmac.new(secret, raw_body, hashlib.sha1).hexdigest()
        return hmac.compare_digest(expected, (signature_header or "").strip())

    def status_without_network(self) -> IntegrationStatus:
        missing = self.missing_env_vars()
        if missing:
            return IntegrationStatus(
                provider="vercel",
                configured=False,
                capability_state=HonestCapabilityState.DEFINED_NOT_INSTALLED,
                live_verified=False,
                missing_env_vars=missing,
                detail="VERCEL_TOKEN not configured; vercel.json and api/index.py are ready for deployment.",
            )
        return IntegrationStatus(
            provider="vercel",
            configured=True,
            capability_state=HonestCapabilityState.INSTALLED,
            live_verified=False,
            endpoint=f"{self.BASE_URL}/v2/user",
            detail="VERCEL_TOKEN configured; run live verification to confirm API token validity.",
        )

    def verify_live(self, timeout_seconds: float = 8.0) -> IntegrationStatus:
        if not self.is_configured():
            return self.status_without_network()

        if self._settings.vercel_project_id.strip():
            endpoint = f"{self.BASE_URL}/v9/projects/{self._settings.vercel_project_id.strip()}"
        else:
            endpoint = f"{self.BASE_URL}/v2/user"

        started = time.perf_counter()
        try:
            if self._client is not None:
                resp = self._client.get(endpoint, headers=self._headers(), timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.get(endpoint, headers=self._headers())
            latency_ms = int((time.perf_counter() - started) * 1000)
            if 200 <= resp.status_code < 300:
                return IntegrationStatus(
                    provider="vercel",
                    configured=True,
                    capability_state=HonestCapabilityState.AVAILABLE,
                    live_verified=True,
                    endpoint=endpoint,
                    latency_ms=latency_ms,
                    detail="Vercel API authentication verified.",
                )
            return IntegrationStatus(
                provider="vercel",
                configured=True,
                capability_state=HonestCapabilityState.INSTALLED,
                live_verified=False,
                endpoint=endpoint,
                latency_ms=latency_ms,
                detail=classify_http_error(resp.status_code),
            )
        except httpx.TimeoutException:
            return IntegrationStatus(
                provider="vercel",
                configured=True,
                capability_state=HonestCapabilityState.INSTALLED,
                live_verified=False,
                endpoint=endpoint,
                detail="PROVIDER_TIMEOUT: Vercel API timed out.",
            )
        except httpx.HTTPError as exc:
            return IntegrationStatus(
                provider="vercel",
                configured=True,
                capability_state=HonestCapabilityState.INSTALLED,
                live_verified=False,
                endpoint=endpoint,
                detail=f"PROVIDER_NETWORK_UNAVAILABLE: {type(exc).__name__}",
            )
