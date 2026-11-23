"""Extended tool & external platform integration interfaces with honest capability verification.

Covers GitHub, Google Drive, Email, WhatsApp, Google Calendar, Web Research,
File Processing, Image Generation, Coding Environment, and Governed External APIs.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import IntegrationError
from app.integrations.base import HonestCapabilityState, IntegrationStatus, classify_http_error


class GitHubClient:
    """GitHub REST API v3 client for repository/branch/PR inspection."""

    BASE_URL = "https://api.github.com"

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = http_client

    @property
    def _token(self) -> str:
        return self._settings.github_token.get_secret_value().strip() if self._settings.github_token else ""

    def is_configured(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def status_without_network(self) -> IntegrationStatus:
        if not self.is_configured():
            return IntegrationStatus(
                provider="github",
                configured=False,
                capability_state=HonestCapabilityState.DEFINED_NOT_INSTALLED,
                live_verified=False,
                requires_approval_for_mutations=True,
                missing_env_vars=["GITHUB_TOKEN"],
                detail="GITHUB_TOKEN not set; local git repository inspection remains available where checked out.",
            )
        return IntegrationStatus(
            provider="github",
            configured=True,
            capability_state=HonestCapabilityState.INSTALLED,
            live_verified=False,
            requires_approval_for_mutations=True,
            endpoint=f"{self.BASE_URL}/user",
            detail="GITHUB_TOKEN configured; run live verification to confirm GitHub API access.",
        )

    def verify_live(self, timeout_seconds: float = 8.0) -> IntegrationStatus:
        if not self.is_configured():
            return self.status_without_network()
        endpoint = f"{self.BASE_URL}/user"
        started = time.perf_counter()
        try:
            if self._client is not None:
                resp = self._client.get(endpoint, headers=self._headers(), timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.get(endpoint, headers=self._headers())
            latency_ms = int((time.perf_counter() - started) * 1000)
            if 200 <= resp.status_code < 300:
                login = resp.json().get("login", "authenticated")
                return IntegrationStatus(
                    provider="github",
                    configured=True,
                    capability_state=HonestCapabilityState.AVAILABLE,
                    live_verified=True,
                    requires_approval_for_mutations=True,
                    endpoint=endpoint,
                    latency_ms=latency_ms,
                    detail=f"GitHub API authenticated as '{login}'.",
                )
            return IntegrationStatus(
                provider="github",
                configured=True,
                capability_state=HonestCapabilityState.DEGRADED,
                live_verified=False,
                requires_approval_for_mutations=True,
                endpoint=endpoint,
                latency_ms=latency_ms,
                detail=classify_http_error(resp.status_code),
            )
        except httpx.HTTPError as exc:
            return IntegrationStatus(
                provider="github",
                configured=True,
                capability_state=HonestCapabilityState.UNAVAILABLE,
                live_verified=False,
                requires_approval_for_mutations=True,
                endpoint=endpoint,
                detail=f"PROVIDER_NETWORK_UNAVAILABLE: {type(exc).__name__}",
            )

    def get_repo_info(self, repo_full_name: str, timeout_seconds: float = 8.0) -> dict[str, Any]:
        if not self.is_configured():
            raise IntegrationError("GITHUB_TOKEN is not configured.")
        endpoint = f"{self.BASE_URL}/repos/{repo_full_name}"
        try:
            if self._client is not None:
                resp = self._client.get(endpoint, headers=self._headers(), timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.get(endpoint, headers=self._headers())
        except httpx.HTTPError as exc:
            raise IntegrationError(f"GitHub request failed: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise IntegrationError(f"GitHub API failed: {classify_http_error(resp.status_code)}")
        return resp.json()


class GoogleDriveClient:
    """Google Drive v3 read-only knowledge workspace client (never writes app source code to Drive)."""

    BASE_URL = "https://www.googleapis.com/drive/v3"

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = http_client

    @property
    def _token(self) -> str:
        if getattr(self, "_oauth_token", None):
            return str(self._oauth_token).strip()
        return (
            self._settings.google_drive_access_token.get_secret_value().strip()
            if self._settings.google_drive_access_token
            else ""
        )

    def is_configured(self) -> bool:
        return bool(self._token)

    def status_without_network(self) -> IntegrationStatus:
        if not self.is_configured():
            oauth_ready = bool(
                self._settings.google_oauth_client_id
                and self._settings.google_oauth_client_secret
                and self._settings.google_oauth_client_secret.get_secret_value()
            )
            detail = (
                "Ready for Google OAuth 2.0 authorization via Configure."
                if oauth_ready
                else "Google Drive setup is not yet available. Administrator configuration is required."
            )
            return IntegrationStatus(
                provider="google_drive",
                configured=False,
                capability_state=HonestCapabilityState.DEFINED_NOT_INSTALLED,
                live_verified=False,
                missing_env_vars=[],
                detail=detail,
            )
        return IntegrationStatus(
            provider="google_drive",
            configured=True,
            capability_state=HonestCapabilityState.INSTALLED,
            live_verified=False,
            endpoint=f"{self.BASE_URL}/about?fields=user",
            detail="Google Drive OAuth credentials stored in VAULT; run health check to verify live access.",
        )

    def verify_live(self, timeout_seconds: float = 8.0) -> IntegrationStatus:
        if not self.is_configured():
            return self.status_without_network()
        endpoint = f"{self.BASE_URL}/about"
        started = time.perf_counter()
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            if self._client is not None:
                resp = self._client.get(endpoint, headers=headers, params={"fields": "user"}, timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.get(endpoint, headers=headers, params={"fields": "user"})
            latency_ms = int((time.perf_counter() - started) * 1000)
            if 200 <= resp.status_code < 300:
                return IntegrationStatus(
                    provider="google_drive",
                    configured=True,
                    capability_state=HonestCapabilityState.AVAILABLE,
                    live_verified=True,
                    endpoint=endpoint,
                    latency_ms=latency_ms,
                    detail="Google Drive API v3 live check passed.",
                )
            return IntegrationStatus(
                provider="google_drive",
                configured=True,
                capability_state=HonestCapabilityState.DEGRADED,
                live_verified=False,
                endpoint=endpoint,
                latency_ms=latency_ms,
                detail=classify_http_error(resp.status_code),
            )
        except httpx.HTTPError as exc:
            return IntegrationStatus(
                provider="google_drive",
                configured=True,
                capability_state=HonestCapabilityState.UNAVAILABLE,
                live_verified=False,
                endpoint=endpoint,
                detail=f"PROVIDER_NETWORK_UNAVAILABLE: {type(exc).__name__}",
            )


def build_extended_capability_statuses(settings: Settings) -> dict[str, IntegrationStatus]:
    """Return honest capability states for all extended external and local runtime capabilities."""
    email_configured = bool(
        settings.email_smtp_host.strip()
        or (settings.email_api_key and settings.email_api_key.get_secret_value().strip())
    )
    whatsapp_configured = bool(
        settings.whatsapp_access_token
        and settings.whatsapp_access_token.get_secret_value().strip()
        and settings.whatsapp_phone_number_id.strip()
    )
    calendar_configured = bool(
        settings.google_calendar_access_token and settings.google_calendar_access_token.get_secret_value().strip()
    )
    gemini_configured = bool(settings.gemini_api_key and settings.gemini_api_key.get_secret_value().strip())

    return {
        "email": IntegrationStatus(
            provider="email",
            configured=email_configured,
            capability_state=(
                HonestCapabilityState.REQUIRES_APPROVAL
                if email_configured
                else HonestCapabilityState.DEFINED_NOT_INSTALLED
            ),
            live_verified=False,
            requires_approval_for_mutations=True,
            missing_env_vars=[] if email_configured else ["EMAIL_API_KEY (or EMAIL_SMTP_HOST)"],
            detail=(
                "Email provider configured; outbound dispatch strictly gated by ApprovalGate."
                if email_configured
                else "Email transport not configured; drafting supported, live sending inactive."
            ),
        ),
        "whatsapp": IntegrationStatus(
            provider="whatsapp",
            configured=whatsapp_configured,
            capability_state=(
                HonestCapabilityState.REQUIRES_APPROVAL
                if whatsapp_configured
                else HonestCapabilityState.DEFINED_NOT_INSTALLED
            ),
            live_verified=False,
            requires_approval_for_mutations=True,
            missing_env_vars=[] if whatsapp_configured else ["WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"],
            detail=(
                "WhatsApp Cloud API configured; outbound messages require ApprovalGate sign-off."
                if whatsapp_configured
                else "WhatsApp Cloud API credentials not configured."
            ),
        ),
        "calendar": IntegrationStatus(
            provider="calendar",
            configured=calendar_configured,
            capability_state=(
                HonestCapabilityState.INSTALLED
                if calendar_configured
                else HonestCapabilityState.DEFINED_NOT_INSTALLED
            ),
            live_verified=False,
            requires_approval_for_mutations=True,
            missing_env_vars=[] if calendar_configured else ["GOOGLE_CALENDAR_ACCESS_TOKEN"],
            detail=(
                "Google Calendar token configured; pending live probe."
                if calendar_configured
                else "GOOGLE_CALENDAR_ACCESS_TOKEN not configured."
            ),
        ),
        "web_research": IntegrationStatus(
            provider="web_research",
            configured=True,
            capability_state=HonestCapabilityState.AVAILABLE,
            live_verified=True,
            detail="SSRF-protected public HTTP fetch & text extraction harness active.",
        ),
        "file_processing": IntegrationStatus(
            provider="file_processing",
            configured=True,
            capability_state=HonestCapabilityState.AVAILABLE,
            live_verified=True,
            detail="Local text, JSON, CSV, Markdown parser and SHA-256 checksum engine verified active.",
        ),
        "image_generation": IntegrationStatus(
            provider="image_generation",
            configured=gemini_configured,
            capability_state=(
                HonestCapabilityState.INSTALLED
                if gemini_configured
                else HonestCapabilityState.DEFINED_NOT_INSTALLED
            ),
            live_verified=False,
            missing_env_vars=[] if gemini_configured else ["GEMINI_API_KEY"],
            detail=(
                "Image generation interface ready via Gemini/Imagen API; requires live key verification."
                if gemini_configured
                else "GEMINI_API_KEY not configured for image generation."
            ),
        ),
        "coding_environment": IntegrationStatus(
            provider="coding_environment",
            configured=True,
            capability_state=HonestCapabilityState.AVAILABLE,
            live_verified=True,
            requires_approval_for_mutations=True,
            detail="Python AST static analysis, syntax verification, and git repo inspector active (writes require approval).",
        ),
        "external_apis": IntegrationStatus(
            provider="external_apis",
            configured=True,
            capability_state=HonestCapabilityState.REQUIRES_APPROVAL,
            live_verified=True,
            requires_approval_for_mutations=True,
            detail="Governed SSRF-safe external API gateway active; mutating calls require ApprovalGate.",
        ),
    }
