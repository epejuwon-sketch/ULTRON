"""Cloudflare API integration client: token verify, DNS zones/records, Workers, KV, R2, analytics, and security config."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import IntegrationError
from app.integrations.base import HonestCapabilityState, IntegrationStatus, classify_http_error


class CloudflareClient:
    """Cloudflare REST API v4 client for DNS, Workers, KV, R2, analytics, and security monitoring."""

    BASE_URL = "https://api.cloudflare.com/client/v4"

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None, token_override: str | None = None) -> None:
        self._settings = settings
        self._client = http_client
        self._token_override = token_override

    @property
    def _token(self) -> str:
        if self._token_override:
            return self._token_override.strip()
        if self._settings.cloudflare_api_token:
            return self._settings.cloudflare_api_token.get_secret_value().strip()
        return ""

    def missing_env_vars(self) -> list[str]:
        return [] if self._token else ["CLOUDFLARE_API_TOKEN"]

    def is_configured(self) -> bool:
        return bool(self._token)

    def _headers(self, content_type: str = "application/json") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": content_type,
        }

    def _req(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        content: str | bytes | None = None,
        content_type: str = "application/json",
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise IntegrationError("CLOUDFLARE_API_TOKEN is not configured.")
        url = f"{self.BASE_URL}{path}"
        try:
            if self._client is not None:
                resp = self._client.request(
                    method, url, headers=self._headers(content_type), params=params, json=json_body, content=content, timeout=timeout
                )
            else:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.request(
                        method, url, headers=self._headers(content_type), params=params, json=json_body, content=content
                    )
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Cloudflare network error: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise IntegrationError(f"Cloudflare API error on {path}: {classify_http_error(resp.status_code)}")
        return resp.json() if resp.content else {"success": True}

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
            data = self._req("GET", "/user/tokens/verify", timeout=timeout_seconds)
            latency_ms = int((time.perf_counter() - started) * 1000)
            if data.get("success") is True:
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
                capability_state=HonestCapabilityState.DEGRADED,
                live_verified=False,
                endpoint=endpoint,
                latency_ms=latency_ms,
                detail="Cloudflare token verification returned success=false.",
            )
        except IntegrationError as exc:
            return IntegrationStatus(
                provider="cloudflare",
                configured=True,
                capability_state=HonestCapabilityState.DEGRADED,
                live_verified=False,
                endpoint=endpoint,
                detail=str(exc),
            )

    def list_zones(self) -> list[dict[str, Any]]:
        return self._req("GET", "/zones").get("result", [])

    def list_dns_records(self, zone_id: str | None = None) -> list[dict[str, Any]]:
        zid = zone_id or self._settings.cloudflare_zone_id.strip()
        if not zid:
            raise IntegrationError("CLOUDFLARE_ZONE_ID is required to list DNS records.")
        return self._req("GET", f"/zones/{zid}/dns_records").get("result", [])

    def list_workers(self, account_id: str | None = None) -> list[dict[str, Any]]:
        aid = account_id or self._settings.cloudflare_account_id.strip()
        if not aid:
            raise IntegrationError("CLOUDFLARE_ACCOUNT_ID is required to list Workers.")
        return self._req("GET", f"/accounts/{aid}/workers/scripts").get("result", [])

    def list_kv_namespaces(self, account_id: str | None = None) -> list[dict[str, Any]]:
        aid = account_id or self._settings.cloudflare_account_id.strip()
        if not aid:
            raise IntegrationError("CLOUDFLARE_ACCOUNT_ID is required to list KV namespaces.")
        return self._req("GET", f"/accounts/{aid}/storage/kv/namespaces").get("result", [])

    def list_r2_buckets(self, account_id: str | None = None) -> list[dict[str, Any]]:
        aid = account_id or self._settings.cloudflare_account_id.strip()
        if not aid:
            raise IntegrationError("CLOUDFLARE_ACCOUNT_ID is required to list R2 buckets.")
        res = self._req("GET", f"/accounts/{aid}/r2/buckets").get("result", {})
        return res.get("buckets", []) if isinstance(res, dict) else res

    def get_zone_security_settings(self, zone_id: str | None = None) -> dict[str, Any]:
        zid = zone_id or self._settings.cloudflare_zone_id.strip()
        if not zid:
            raise IntegrationError("CLOUDFLARE_ZONE_ID is required for security inspection.")
        ssl = self._req("GET", f"/zones/{zid}/settings/ssl").get("result", {})
        sec_level = self._req("GET", f"/zones/{zid}/settings/security_level").get("result", {})
        return {"zone_id": zid, "ssl": ssl, "security_level": sec_level}

    def kv_put(self, key: str, value: str, *, ttl_seconds: int | None = None) -> dict[str, Any]:
        account_id = self._settings.cloudflare_account_id.strip()
        namespace_id = self._settings.cloudflare_kv_namespace_id.strip()
        if not (self.is_configured() and account_id and namespace_id):
            raise IntegrationError(
                "Cloudflare KV requires CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, and CLOUDFLARE_KV_NAMESPACE_ID."
            )
        params = {"expiration_ttl": ttl_seconds} if ttl_seconds else None
        return self._req(
            "PUT",
            f"/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/values/{key}",
            params=params,
            content=value,
            content_type="text/plain",
        )
