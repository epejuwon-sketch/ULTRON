"""Unified 14-provider capability registry for ULTRON OS 2026."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.integrations.cloudflare import CloudflareClient
from app.integrations.extended import GitHubClient, GoogleDriveClient, build_extended_capability_statuses
from app.integrations.gemini import GeminiClient
from app.integrations.supabase import SupabaseClient
from app.integrations.vercel import VercelClient


class IntegrationRegistry:
    """Aggregates core cloud clients + extended capability interfaces with honest live verification."""

    CORE_PROVIDERS = ("supabase", "gemini", "vercel", "cloudflare")

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.supabase = SupabaseClient(settings, http_client=http_client)
        self.gemini = GeminiClient(settings, http_client=http_client)
        self.vercel = VercelClient(settings, http_client=http_client)
        self.cloudflare = CloudflareClient(settings, http_client=http_client)
        self.github = GitHubClient(settings, http_client=http_client)
        self.google_drive = GoogleDriveClient(settings, http_client=http_client)

    def get_static_status(self) -> dict[str, Any]:
        """Return configuration status across all 14 capabilities without outbound network calls."""
        core = {
            "supabase": self.supabase.status_without_network().to_dict(),
            "gemini": self.gemini.status_without_network().to_dict(),
            "vercel": self.vercel.status_without_network().to_dict(),
            "cloudflare": self.cloudflare.status_without_network().to_dict(),
        }
        extended = {
            "github": self.github.status_without_network().to_dict(),
            "google_drive": self.google_drive.status_without_network().to_dict(),
            **{k: v.to_dict() for k, v in build_extended_capability_statuses(self.settings).items()},
        }
        all_capabilities = {**core, **extended}
        return {
            "database_backend": self.settings.database_backend,
            "providers": core,
            "capabilities": all_capabilities,
            "configured_count": sum(1 for p in core.values() if p["configured"]),
            "total_providers": len(core),
            "total_capabilities": len(all_capabilities),
        }

    def verify_all_live(self, timeout_seconds: float = 8.0) -> dict[str, Any]:
        """Run live verification probes against all configured network providers honestly."""
        core = {
            "supabase": self.supabase.verify_live(timeout_seconds=timeout_seconds).to_dict(),
            "gemini": self.gemini.verify_live(timeout_seconds=timeout_seconds).to_dict(),
            "vercel": self.vercel.verify_live(timeout_seconds=timeout_seconds).to_dict(),
            "cloudflare": self.cloudflare.verify_live(timeout_seconds=timeout_seconds).to_dict(),
        }
        extended = {
            "github": self.github.verify_live(timeout_seconds=timeout_seconds).to_dict(),
            "google_drive": self.google_drive.verify_live(timeout_seconds=timeout_seconds).to_dict(),
            **{k: v.to_dict() for k, v in build_extended_capability_statuses(self.settings).items()},
        }
        all_capabilities = {**core, **extended}
        return {
            "database_backend": self.settings.database_backend,
            "providers": core,
            "capabilities": all_capabilities,
            "configured_count": sum(1 for p in core.values() if p["configured"]),
            "live_verified_count": sum(1 for p in core.values() if p["live_verified"]),
            "total_providers": len(core),
            "total_capabilities": len(all_capabilities),
            "available_capabilities": sum(
                1 for c in all_capabilities.values() if c["capability_state"] == "AVAILABLE"
            ),
        }
