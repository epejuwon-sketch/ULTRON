"""Cloudflare API integration client (token verification, KV helpers, Turnstile verification)."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import IntegrationError
from app.integrations.base import HonestCapabilityState, IntegrationStatus, classify_http_error


class CloudflareClient:
    """Cloudflare REST API client for edge gateway verification, KV, and Turnstile."""

    BASE_URL = "https://api.cloudflare.com/client/v4"

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = http_client

    @property
    def _token(self) -> str:
        if self._settings.cloudflare_api_token:
            return self._settings.cloudflare_api_token.get_secret_value().strip()
        return ""

    def missing_env_vars(self) -> list[str]:
        return [] if self._token else ["CLOUDFLARE_API_TOKEN"]

    def is_configured(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def status_without_network(self) -> IntegrationStatus:
        missing = self.missing_env_vars()
        if missing:
            return IntegrationStatus(
                provider="cloudflare",
                configured=False,
                capability_state=HonestCapabilityState.DEFINED_NOT_INSTALLED,
                live_verified=False,
                missing_env_vars=missing,
                detail="CLOUDFLARE_API_TOKEN not configured; cloudflare/worker.ts edge proxy template is ready.",
            )
        return IntegrationStatus(
            provider="cloudflare",
            configured=True,
            capability_state=HonestCapabilityState.INSTALLED,
            live_verified=False,
            endpoint=f"{self.BASE_URL}/user/tokens/verify",
            detail="CLOUDFLARE_API_TOKEN configured; run live verification to confirm token status.",
        )

    def verify_live(self, timeout_seconds: float = 8.0) -> IntegrationStatus:
        if not self.is_configured():
            return self.status_without_network()

        endpoint = f"{self.BASE_URL}/user/tokens/verify"
        started = time.perf_counter()
        try:
            if self._client is not None:
                resp = self._client.get(endpoint, headers=self._headers(), timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.get(endpoint, headers=self._headers())
            latency_ms = int((time.perf_counter() - started) * 1000)
            if 200 <= resp.status_code < 300 and resp.json().get("success") is True:
                return IntegrationStatus(
                    provider="cloudflare",
                    configured=True,
                    capability_state=HonestCapabilityState.AVAILABLE,
                    live_verified=True,
                    endpoint=endpoint,
                    latency_ms=latency_ms,
                    detail="Cloudflare API token verified active.",
                )
            return IntegrationStatus(
                provider="cloudflare",
                configured=True,
                capability_state=HonestCapabilityState.INSTALLED,
                live_verified=False,
                endpoint=endpoint,
                latency_ms=latency_ms,
                detail=classify_http_error(resp.status_code),
            )
        except httpx.TimeoutException:
            return IntegrationStatus(
                provider="cloudflare",
                configured=True,
                capability_state=HonestCapabilityState.INSTALLED,
                live_verified=False,
                endpoint=endpoint,
                detail="PROVIDER_TIMEOUT: Cloudflare API timed out.",
            )
        except httpx.HTTPError as exc:
            return IntegrationStatus(
                provider="cloudflare",
                configured=True,
                capability_state=HonestCapabilityState.INSTALLED,
                live_verified=False,
                endpoint=endpoint,
                detail=f"PROVIDER_NETWORK_UNAVAILABLE: {type(exc).__name__}",
            )

    def kv_put(self, key: str, value: str, *, ttl_seconds: int | None = None) -> dict[str, Any]:
        """Write a value to Cloudflare Workers KV when account + namespace are configured."""
        account_id = self._settings.cloudflare_account_id.strip()
        namespace_id = self._settings.cloudflare_kv_namespace_id.strip()
        if not (self.is_configured() and account_id and namespace_id):
            raise IntegrationError(
                "Cloudflare KV requires CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, and CLOUDFLARE_KV_NAMESPACE_ID."
            )
        endpoint = f"{self.BASE_URL}/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/{key}"
        params = {"expiration_ttl": ttl_seconds} if ttl_seconds else None
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "text/plain"}
        try:
            if self._client is not None:
                resp = self._client.put(endpoint, headers=headers, params=params, content=value, timeout=10.0)
            else:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.put(endpoint, headers=headers, params=params, content=value)
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Cloudflare KV write failed: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise IntegrationError(f"Cloudflare KV write failed: {classify_http_error(resp.status_code)}")
        return resp.json()
