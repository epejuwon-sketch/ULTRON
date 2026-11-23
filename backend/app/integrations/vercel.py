"""Vercel API integration client: projects, deployments, build logs, domains, env metadata, and webhook verification."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import IntegrationError
from app.integrations.base import HonestCapabilityState, IntegrationStatus, classify_http_error


class VercelClient:
    """Vercel deployment, project, domain, build log, and env metadata client."""

    BASE_URL = "https://api.vercel.com"

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None, token_override: str | None = None) -> None:
        self._settings = settings
        self._client = http_client
        self._token_override = token_override

    @property
    def _token(self) -> str:
        if self._token_override:
            return self._token_override.strip()
        if self._settings.vercel_token:
            return self._settings.vercel_token.get_secret_value().strip()
        return ""

    def missing_env_vars(self) -> list[str]:
        return [] if self._token else ["VERCEL_TOKEN"]

    def is_configured(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _req(self, method: str, path: str, *, params: dict[str, Any] | None = None, timeout: float = 10.0) -> Any:
        if not self.is_configured():
            raise IntegrationError("VERCEL_TOKEN is not configured.")
        url = f"{self.BASE_URL}{path}"
        merged_params = dict(params or {})
        if self._settings.vercel_org_id.strip():
            merged_params.setdefault("teamId", self._settings.vercel_org_id.strip())
        try:
            if self._client is not None:
                resp = self._client.request(method, url, headers=self._headers(), params=merged_params or None, timeout=timeout)
            else:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.request(method, url, headers=self._headers(), params=merged_params or None)
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Vercel network error: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise IntegrationError(f"Vercel API error on {path}: {classify_http_error(resp.status_code)}")
        return resp.json() if resp.content else {}

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

        path = (
            f"/v9/projects/{self._settings.vercel_project_id.strip()}"
            if self._settings.vercel_project_id.strip()
            else "/v2/user"
        )
        endpoint = f"{self.BASE_URL}{path}"
        started = time.perf_counter()
        try:
            user_data = self._req("GET", path, timeout=timeout_seconds)
            projects_data = self._req("GET", "/v9/projects", params={"limit": 5}, timeout=timeout_seconds)
            proj_count = len(projects_data.get("projects", [])) if isinstance(projects_data, dict) else 0
            latency_ms = int((time.perf_counter() - started) * 1000)
            acct = user_data.get("user", {}).get("username") if isinstance(user_data, dict) else None
            acct_label = f" as '{acct}'" if acct else ""
            return IntegrationStatus(
                provider="vercel",
                configured=True,
                capability_state=HonestCapabilityState.AVAILABLE,
                live_verified=True,
                endpoint=endpoint,
                latency_ms=latency_ms,
                detail=f"Vercel account{acct_label} and project discovery verified ({proj_count} project(s) visible).",
            )
        except IntegrationError as exc:
            return IntegrationStatus(
                provider="vercel",
                configured=True,
                capability_state=HonestCapabilityState.DEGRADED,
                live_verified=False,
                endpoint=endpoint,
                detail=str(exc),
            )

    def list_projects(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._req("GET", "/v9/projects", params={"limit": limit}).get("projects", [])

    def list_deployments(self, project_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        pid = project_id or self._settings.vercel_project_id.strip()
        if pid:
            params["projectId"] = pid
        return self._req("GET", "/v6/deployments", params=params).get("deployments", [])

    def get_deployment_status(self, deployment_id: str) -> dict[str, Any]:
        return self._req("GET", f"/v13/deployments/{deployment_id}")

    def get_deployment_events(self, deployment_id: str) -> list[dict[str, Any]]:
        data = self._req("GET", f"/v3/deployments/{deployment_id}/events")
        return data if isinstance(data, list) else data.get("events", [])

    def list_domains(self, project_id: str | None = None) -> list[dict[str, Any]]:
        pid = project_id or self._settings.vercel_project_id.strip()
        if not pid:
            raise IntegrationError("Vercel project_id is required to list domains.")
        return self._req("GET", f"/v9/projects/{pid}/domains").get("domains", [])

    def list_env_metadata(self, project_id: str | None = None) -> list[dict[str, Any]]:
        """List environment variable names & targets only — never exposes decrypted values."""
        pid = project_id or self._settings.vercel_project_id.strip()
        if not pid:
            raise IntegrationError("Vercel project_id is required to list environment variables.")
        envs = self._req("GET", f"/v9/projects/{pid}/env").get("envs", [])
        return [
            {"id": e.get("id"), "key": e.get("key"), "target": e.get("target", []), "type": e.get("type")}
            for e in envs
        ]
