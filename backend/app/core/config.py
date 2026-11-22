"""Secure environment variable management for ULTRON OS 2026.

All configuration is loaded via Pydantic Settings with strict production guards
so placeholder secrets are rejected in production and credentials are never
serialized into logs or status responses.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_DEV_EPHEMERAL_JWT = secrets.token_urlsafe(48)
_DEV_EPHEMERAL_VAULT = secrets.token_urlsafe(48)


class Settings(BaseSettings):
    """Typed runtime settings loaded from environment variables and optional `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime ---
    ultron_env: Literal["development", "test", "staging", "production"] = Field(
        default="development", alias="ULTRON_ENV"
    )
    app_name: str = Field(default="ULTRON OS 2026 Backend", alias="ULTRON_APP_NAME")
    app_version: str = Field(default="2026.1.0", alias="ULTRON_APP_VERSION")
    host: str = Field(default="0.0.0.0", alias="ULTRON_HOST")
    port: int = Field(default=8000, alias="ULTRON_PORT")
    log_level: str = Field(default="INFO", alias="ULTRON_LOG_LEVEL")
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        alias="ULTRON_CORS_ORIGINS",
    )

    # --- ARGON Security ---
    jwt_secret: SecretStr = Field(
        default_factory=lambda: SecretStr(_DEV_EPHEMERAL_JWT),
        alias="ULTRON_JWT_SECRET",
    )
    vault_master_key: SecretStr = Field(
        default_factory=lambda: SecretStr(_DEV_EPHEMERAL_VAULT),
        alias="ULTRON_VAULT_MASTER_KEY",
    )
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=86400, alias="ULTRON_ACCESS_TOKEN_TTL_SECONDS")
    refresh_token_ttl_days: int = Field(default=7, ge=1, le=90, alias="ULTRON_REFRESH_TOKEN_TTL_DAYS")
    max_failed_logins: int = Field(default=5, ge=3, le=20, alias="ULTRON_MAX_FAILED_LOGINS")
    lockout_minutes: int = Field(default=15, ge=1, le=1440, alias="ULTRON_LOCKOUT_MINUTES")

    # --- Governance ---
    approval_soft_limit_usd: float = Field(default=50.0, ge=0.0, alias="ULTRON_APPROVAL_SOFT_LIMIT_USD")
    default_tenant_id: str = Field(default="TENANT-ULTRON-01", alias="ULTRON_DEFAULT_TENANT_ID")

    # --- Persistence ---
    database_url: str = Field(default="", alias="ULTRON_DATABASE_URL")
    sqlite_path: str = Field(default="./data/ultron_os_2026.db", alias="ULTRON_SQLITE_PATH")

    # --- Supabase ---
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_anon_key: SecretStr | None = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: SecretStr | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")

    # --- Google Gemini API ---
    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        alias="GEMINI_BASE_URL",
    )
    gemini_model_fast: str = Field(default="gemini-2.0-flash-lite", alias="GEMINI_MODEL_FAST")
    gemini_model_standard: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL_STANDARD")
    gemini_model_reasoning: str = Field(default="gemini-2.5-pro", alias="GEMINI_MODEL_REASONING")
    gemini_model_embedding: str = Field(default="text-embedding-004", alias="GEMINI_MODEL_EMBEDDING")

    # --- Vercel ---
    vercel_token: SecretStr | None = Field(default=None, alias="VERCEL_TOKEN")
    vercel_project_id: str = Field(default="", alias="VERCEL_PROJECT_ID")
    vercel_org_id: str = Field(default="", alias="VERCEL_ORG_ID")
    vercel_webhook_secret: SecretStr | None = Field(default=None, alias="VERCEL_WEBHOOK_SECRET")

    # --- Cloudflare ---
    cloudflare_api_token: SecretStr | None = Field(default=None, alias="CLOUDFLARE_API_TOKEN")
    cloudflare_account_id: str = Field(default="", alias="CLOUDFLARE_ACCOUNT_ID")
    cloudflare_zone_id: str = Field(default="", alias="CLOUDFLARE_ZONE_ID")
    cloudflare_kv_namespace_id: str = Field(default="", alias="CLOUDFLARE_KV_NAMESPACE_ID")
    cloudflare_r2_bucket: str = Field(default="", alias="CLOUDFLARE_R2_BUCKET")
    cloudflare_turnstile_secret_key: SecretStr | None = Field(
        default=None, alias="CLOUDFLARE_TURNSTILE_SECRET_KEY"
    )

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "Settings":
        if self.ultron_env == "production":
            for label, secret in (
                ("ULTRON_JWT_SECRET", self.jwt_secret.get_secret_value()),
                ("ULTRON_VAULT_MASTER_KEY", self.vault_master_key.get_secret_value()),
            ):
                if (
                    len(secret) < 32
                    or secret.startswith("replace-with-")
                    or secret in (_DEV_EPHEMERAL_JWT, _DEV_EPHEMERAL_VAULT)
                ):
                    raise ValueError(
                        f"{label} must be explicitly configured with >= 32 cryptographically strong characters in production."
                    )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def effective_database_url(self) -> str:
        url = self.database_url.strip()
        if url:
            return url
        return f"sqlite:///{self.sqlite_path}"

    @property
    def database_backend(self) -> str:
        url = self.effective_database_url.lower()
        if url.startswith("postgresql") or url.startswith("postgres"):
            return "postgresql"
        return "sqlite"

    def safe_summary(self) -> dict[str, Any]:
        """Return non-sensitive runtime configuration metadata safe for diagnostics."""
        return {
            "env": self.ultron_env,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "database_backend": self.database_backend,
            "approval_soft_limit_usd": self.approval_soft_limit_usd,
            "default_tenant_id": self.default_tenant_id,
            "integrations_configured": {
                "supabase": bool(self.supabase_url.strip() and (self.supabase_service_role_key or self.supabase_anon_key)),
                "gemini": bool(self.gemini_api_key and self.gemini_api_key.get_secret_value().strip()),
                "vercel": bool(self.vercel_token and self.vercel_token.get_secret_value().strip()),
                "cloudflare": bool(self.cloudflare_api_token and self.cloudflare_api_token.get_secret_value().strip()),
            },
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor; call `get_settings.cache_clear()` in tests after env overrides."""
    return Settings()
