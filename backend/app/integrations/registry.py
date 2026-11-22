"""Unified registry aggregating all external ULTRON OS 2026 integrations."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.integrations.cloudflare import CloudflareClient
from app.integrations.gemini import GeminiClient
from app.integrations.supabase import SupabaseClient
from app.integrations.vercel import VercelClient


class IntegrationRegistry:
    """Provides configured clients and honest verification across Supabase, Gemini, Vercel, and Cloudflare."""

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.supabase = SupabaseClient(settings, http_client=http_client)
        self.gemini = GeminiClient(settings, http_client=http_client)
        self.vercel = VercelClient(settings, http_client=http_client)
        self.cloudflare = CloudflareClient(settings, http_client=http_client)

    def get_static_status(self) -> dict[str, Any]:
        """Return configuration status without making outbound network calls."""
        providers = {
            "supabase": self.supabase.status_without_network().to_dict(),
            "gemini": self.gemini.status_without_network().to_dict(),
            "vercel": self.vercel.status_without_network().to_dict(),
            "cloudflare": self.cloudflare.status_without_network().to_dict(),
        }
        return {
            "database_backend": self.settings.database_backend,
            "providers": providers,
            "configured_count": sum(1 for p in providers.values() if p["configured"]),
            "total_providers": len(providers),
        }

    def verify_all_live(self, timeout_seconds: float = 8.0) -> dict[str, Any]:
        """Run live verification probes against all configured providers honestly."""
        results = {
            "supabase": self.supabase.verify_live(timeout_seconds=timeout_seconds).to_dict(),
            "gemini": self.gemini.verify_live(timeout_seconds=timeout_seconds).to_dict(),
            "vercel": self.vercel.verify_live(timeout_seconds=timeout_seconds).to_dict(),
            "cloudflare": self.cloudflare.verify_live(timeout_seconds=timeout_seconds).to_dict(),
        }
        return {
            "database_backend": self.settings.database_backend,
            "providers": results,
            "configured_count": sum(1 for p in results.values() if p["configured"]),
            "live_verified_count": sum(1 for p in results.values() if p["live_verified"]),
            "total_providers": len(results),
        }
