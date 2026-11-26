"""Supabase REST, Auth, and Storage integration client with honest live verification."""

from __future__ import annotations

import re

import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import IntegrationError
from app.integrations.base import HonestCapabilityState, IntegrationStatus, classify_http_error


class SupabaseClient:
    """Server-side Supabase PostgREST + Storage HTTP client.

    Never exposes the service-role key to frontend responses or logs.
    """

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = http_client

    @property
    def base_url(self) -> str:
        explicit = self._settings.supabase_url.strip().rstrip("/")
        if explicit:
            return explicit
        # Auto-derive Supabase project REST URL from PostgreSQL host if present
        raw_db = self._settings.database_url.strip()
        if "supabase.co" in raw_db or "supabase.com" in raw_db:
            m = re.search(r"postgres\.([a-zA-Z0-9_-]+)[@:]", raw_db)
            if not m:
                m = re.search(r"db\.([a-zA-Z0-9_-]+)\.supabase\.co", raw_db)
            if not m:
                m = re.search(r"//([a-zA-Z0-9_-]+)\.supabase\.co", raw_db)
            if m:
                return f"https://{m.group(1)}.supabase.co"
        return ""

    @property
    def _api_key(self) -> str:
        if self._settings.supabase_service_role_key:
            val = self._settings.supabase_service_role_key.get_secret_value().strip()
            if val:
                return val
        if self._settings.supabase_anon_key:
            val = self._settings.supabase_anon_key.get_secret_value().strip()
            if val:
                return val
        return ""

    def missing_env_vars(self) -> list[str]:
        missing: list[str] = []
        if not self.base_url:
            missing.append("SUPABASE_URL")
        if not self._api_key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY)")
        return missing

    def is_configured(self) -> bool:
        return len(self.missing_env_vars()) == 0

    def _headers(self, content_type: str = "application/json") -> dict[str, str]:
        key = self._api_key
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": content_type,
        }

    def status_without_network(self) -> IntegrationStatus:
        missing = self.missing_env_vars()
        has_pg = self._settings.database_backend == "postgresql"
        if has_pg:
            from app.db.session import check_database_health
            db_ok, db_detail = check_database_health(self._settings)
            if db_ok:
                return IntegrationStatus(
                    provider="supabase",
                    configured=True,
                    capability_state=HonestCapabilityState.AVAILABLE,
                    live_verified=False,
                    endpoint=f"{self.base_url}/rest/v1/" if self.base_url else "postgresql://",
                    missing_env_vars=missing,
                    detail=f"PostgreSQL database connected ({self._settings.database_backend})." + (
                        f" Supabase PostgREST/Storage APIs require {', '.join(missing)}." if missing else ""
                    ),
                )

        if missing:
            detail = (
                "Supabase credentials not configured; configure ULTRON_DATABASE_URL (or DATABASE_URL) with your Supabase Transaction Pooler connection string (*.pooler.supabase.com:6543) in Vercel. Ensure it is scoped to Preview and Production."
                if self._settings.is_deployed_environment
                else "Supabase credentials not configured; local SQLite WAL active unless ULTRON_DATABASE_URL is set."
            )
            return IntegrationStatus(
                provider="supabase",
                configured=False,
                capability_state=HonestCapabilityState.DEFINED_NOT_INSTALLED,
                live_verified=False,
                missing_env_vars=missing,
                detail=detail,
            )
        return IntegrationStatus(
            provider="supabase",
            configured=True,
            capability_state=HonestCapabilityState.INSTALLED,
            live_verified=False,
            endpoint=f"{self.base_url}/rest/v1/",
            detail="Supabase credentials present; run live verification to confirm connectivity.",
        )

    def verify_live(self, timeout_seconds: float = 8.0) -> IntegrationStatus:
        missing = self.missing_env_vars()
        has_pg = self._settings.database_backend == "postgresql"

        # If PostgreSQL is configured, verify direct database connectivity first
        if has_pg:
            from app.db.session import check_database_health
            started = time.perf_counter()
            db_ok, db_detail = check_database_health(self._settings)
            latency_ms = int((time.perf_counter() - started) * 1000)
            if not db_ok:
                return IntegrationStatus(
                    provider="supabase",
                    configured=True,
                    capability_state=HonestCapabilityState.DEGRADED,
                    live_verified=False,
                    endpoint="postgresql://",
                    latency_ms=latency_ms,
                    detail=f"Database connectivity check failed: {db_detail}",
                )
            if missing:
                return IntegrationStatus(
                    provider="supabase",
                    configured=True,
                    capability_state=HonestCapabilityState.AVAILABLE,
                    live_verified=True,
                    endpoint="postgresql://",
                    latency_ms=latency_ms,
                    detail=f"Database ({self._settings.database_backend}) connectivity live verified. PostgREST/Storage APIs require {', '.join(missing)}.",
                )

        if missing:
            return self.status_without_network()

        endpoint = f"{self.base_url}/rest/v1/"
        started = time.perf_counter()
        try:
            if self._client is not None:
                resp = self._client.get(endpoint, headers=self._headers(), timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.get(endpoint, headers=self._headers())
            latency_ms = int((time.perf_counter() - started) * 1000)
            if 200 <= resp.status_code < 300:
                from app.db.session import check_database_health

                db_ok, db_detail = check_database_health(self._settings)
                if not db_ok:
                    return IntegrationStatus(
                        provider="supabase",
                        configured=True,
                        capability_state=HonestCapabilityState.DEGRADED,
                        live_verified=False,
                        endpoint=endpoint,
                        latency_ms=latency_ms,
                        detail=f"Supabase PostgREST responded, but database connectivity check failed: {db_detail}",
                    )
                return IntegrationStatus(
                    provider="supabase",
                    configured=True,
                    capability_state=HonestCapabilityState.AVAILABLE,
                    live_verified=True,
                    endpoint=endpoint,
                    latency_ms=latency_ms,
                    detail=f"Supabase PostgREST and database ({self._settings.database_backend}) connectivity verified.",
                )
            return IntegrationStatus(
                provider="supabase",
                configured=True,
                capability_state=HonestCapabilityState.DEGRADED,
                live_verified=False,
                endpoint=endpoint,
                latency_ms=latency_ms,
                detail=classify_http_error(resp.status_code),
            )
        except httpx.TimeoutException:
            return IntegrationStatus(
                provider="supabase",
                configured=True,
                capability_state=HonestCapabilityState.UNAVAILABLE,
                live_verified=False,
                endpoint=endpoint,
                detail="PROVIDER_TIMEOUT: Supabase did not respond within timeout.",
            )
        except httpx.HTTPError as exc:
            return IntegrationStatus(
                provider="supabase",
                configured=True,
                capability_state=HonestCapabilityState.UNAVAILABLE,
                live_verified=False,
                endpoint=endpoint,
                detail=f"PROVIDER_NETWORK_UNAVAILABLE: {type(exc).__name__}",
            )

    def select_rows(
        self,
        table: str,
        params: dict[str, str] | None = None,
        timeout_seconds: float = 10.0,
    ) -> list[dict[str, Any]]:
        """Query a Supabase PostgREST table using server-side credentials."""
        if not self.is_configured():
            raise IntegrationError("Supabase is not configured.", details={"missing": self.missing_env_vars()})
        endpoint = f"{self.base_url}/rest/v1/{table}"
        try:
            if self._client is not None:
                resp = self._client.get(endpoint, headers=self._headers(), params=params, timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.get(endpoint, headers=self._headers(), params=params)
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Supabase request failed: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise IntegrationError(f"Supabase query failed: {classify_http_error(resp.status_code)}")
        data = resp.json()
        return data if isinstance(data, list) else []

    def storage_list_buckets(self, timeout_seconds: float = 8.0) -> list[dict[str, Any]]:
        """List Supabase Storage buckets using the server-side storage API."""
        if not self.is_configured():
            raise IntegrationError("Supabase Storage is not configured.", details={"missing": self.missing_env_vars()})
        endpoint = f"{self.base_url}/storage/v1/bucket"
        try:
            if self._client is not None:
                resp = self._client.get(endpoint, headers=self._headers(), timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.get(endpoint, headers=self._headers())
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Supabase Storage request failed: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise IntegrationError(f"Supabase Storage list failed: {classify_http_error(resp.status_code)}")
        data = resp.json()
        return data if isinstance(data, list) else []

    def storage_upload_object(
        self,
        *,
        bucket: str | None = None,
        object_path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        timeout_seconds: float = 15.0,
    ) -> dict[str, Any]:
        """Upload binary content to a Supabase Storage bucket."""
        if not self.is_configured():
            raise IntegrationError("Supabase Storage is not configured.", details={"missing": self.missing_env_vars()})
        target_bucket = bucket or self._settings.supabase_storage_bucket
        clean_path = object_path.lstrip("/")
        endpoint = f"{self.base_url}/storage/v1/object/{target_bucket}/{clean_path}"
        headers = self._headers(content_type=content_type)
        headers["x-upsert"] = "true"
        try:
            if self._client is not None:
                resp = self._client.post(endpoint, headers=headers, content=content, timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.post(endpoint, headers=headers, content=content)
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Supabase Storage upload failed: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise IntegrationError(f"Supabase Storage upload failed: {classify_http_error(resp.status_code)}")
        return resp.json() if resp.content else {"bucket": target_bucket, "path": clean_path}

    def storage_create_signed_url(
        self,
        *,
        bucket: str | None = None,
        object_path: str,
        expires_in_seconds: int = 3600,
        timeout_seconds: float = 8.0,
    ) -> dict[str, Any]:
        """Generate a time-limited signed download URL without exposing service credentials."""
        if not self.is_configured():
            raise IntegrationError("Supabase Storage is not configured.", details={"missing": self.missing_env_vars()})
        target_bucket = bucket or self._settings.supabase_storage_bucket
        clean_path = object_path.lstrip("/")
        endpoint = f"{self.base_url}/storage/v1/object/sign/{target_bucket}/{clean_path}"
        try:
            if self._client is not None:
                resp = self._client.post(
                    endpoint,
                    headers=self._headers(),
                    json={"expiresIn": expires_in_seconds},
                    timeout=timeout_seconds,
                )
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.post(endpoint, headers=self._headers(), json={"expiresIn": expires_in_seconds})
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Supabase signed URL request failed: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise IntegrationError(f"Supabase signed URL failed: {classify_http_error(resp.status_code)}")
        return resp.json()
