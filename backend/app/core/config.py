"""Secure environment variable management for ULTRON OS 2026.

All configuration is loaded via Pydantic Settings with strict production guards
so placeholder secrets are rejected in production and credentials are never
serialized into logs or status responses.
"""

from __future__ import annotations

import re
import secrets
from functools import lru_cache
from typing import Any, Literal
from urllib.parse import quote

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.core.exceptions import DatabaseConfigurationError

_DEV_EPHEMERAL_JWT = secrets.token_urlsafe(48)
_DEV_EPHEMERAL_VAULT = secrets.token_urlsafe(48)
_LOCAL_PG_HOSTS = {"localhost", "127.0.0.1", "::1"}
_NON_LIBPQ_QUERY_PARAMS = frozenset(
    {
        "pgbouncer",
        "connection_limit",
        "pool_timeout",
        "schema",
        "supa",
        "prisma",
        "statement_cache_size",
    }
)
_PG_URI_SPLIT_RE = re.compile(
    r"^(postgresql(?:\+[a-z0-9_]+)?://)([^:/@\s]+):(.+)@([A-Za-z0-9._-]+(?::\d+)?(?:/[^?#\s]*)?(?:\?[^#\s]*)?)$",
    re.IGNORECASE,
)
_PCT_ESCAPED_RE = re.compile(r"%[0-9A-Fa-f]{2}")
_PLACEHOLDER_PASSWORDS = frozenset(
    {
        "[your-password]",
        "your-password",
        "your_password",
        "<your-password>",
        "<password>",
        "[password]",
    }
)


def _strip_matching_quotes(value: str) -> str:
    s = value.replace("\u200b", "").replace("\ufeff", "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {"'", '"'}:
        return s[1:-1].strip()
    return s


def _encode_unencoded_pg_password(candidate: str) -> str:
    """Safely percent-encode unencoded reserved characters in a PostgreSQL URI password.

    Splits on the LAST `@` before `host[:port][/db][?query]` so passwords containing
    literal `@`, `#`, `?`, `/`, spaces, or unescaped `%` do not break SQLAlchemy/libpq
    URI parsing, while preserving already percent-encoded `%XX` sequences intact.
    """
    match = _PG_URI_SPLIT_RE.match(candidate)
    if not match:
        return candidate

    scheme, user, raw_pwd, host_and_rest = match.groups()
    if raw_pwd.strip().lower() in _PLACEHOLDER_PASSWORDS:
        raise DatabaseConfigurationError(
            "ULTRON_DATABASE_URL still contains the placeholder password '[YOUR-PASSWORD]'. "
            "Replace it with your actual Supabase database password (without square brackets).",
            details={"required_env_var": "ULTRON_DATABASE_URL", "error_code": "DB_PLACEHOLDER_PASSWORD"},
        )

    # Encode only segments outside valid %XX escapes so already-encoded passwords are never double-encoded.
    needs_encoding = any(ch in raw_pwd for ch in ("@", "#", "?", "/", " ", "\t")) or bool(
        re.search(r"%(?![0-9A-Fa-f]{2})", raw_pwd)
    )
    if not needs_encoding:
        return candidate

    parts: list[str] = []
    pos = 0
    for esc in _PCT_ESCAPED_RE.finditer(raw_pwd):
        if esc.start() > pos:
            parts.append(quote(raw_pwd[pos : esc.start()], safe="!$&'()*+,;=.-_~"))
        parts.append(esc.group(0))
        pos = esc.end()
    if pos < len(raw_pwd):
        parts.append(quote(raw_pwd[pos:], safe="!$&'()*+,;=.-_~"))
    return f"{scheme}{user}:{''.join(parts)}@{host_and_rest}"


def normalize_database_url(
    raw_url: str,
    *,
    allow_sqlite: bool,
    env_label: str = "development",
    is_vercel: bool = False,
) -> str:
    """Validate and normalize a database connection string for SQLAlchemy + psycopg v3.

    - Rejects missing URLs and SQLite URLs whenever `allow_sqlite` is False (production,
      staging, and Vercel preview/production deployments).
    - Strips accidental surrounding quotes and invisible mobile paste characters.
    - Rejects literal `[YOUR-PASSWORD]` placeholders and safely percent-encodes unencoded
      reserved characters (`@`, `#`, `?`, `/`, bare `%`) in PostgreSQL passwords.
    - Normalizes `postgres://`, `postgresql://`, and `postgresql+psycopg2://` to
      `postgresql+psycopg://` to match the installed `psycopg` v3 driver.
    - Strips non-libpq Supabase/Prisma/Vercel pooler query flags (`pgbouncer`, `supa`,
      `connection_limit`, etc.) that cause `psycopg.ProgrammingError: invalid URI query parameter`.
    - Adds `sslmode=require` for remote PostgreSQL hosts (such as Supabase) unless
      `sslmode` is already specified.
    - Never includes raw credentials in raised error messages.
    """
    cleaned = _strip_matching_quotes(raw_url)
    if not cleaned:
        if not allow_sqlite:
            raise DatabaseConfigurationError(
                "ULTRON_DATABASE_URL is required in deployed environments (production, staging, and Vercel deployments). "
                "Configure ULTRON_DATABASE_URL with your Supabase PostgreSQL connection string; SQLite fallback is disabled.",
                details={
                    "env": env_label,
                    "vercel": is_vercel,
                    "required_env_var": "ULTRON_DATABASE_URL",
                },
            )
        return ""

    lower = cleaned.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        raise DatabaseConfigurationError(
            "ULTRON_DATABASE_URL must be a PostgreSQL connection string (postgresql://...), not an HTTP/HTTPS URL. "
            "Copy the PostgreSQL URI from Supabase Project Settings -> Database.",
            details={
                "env": env_label,
                "vercel": is_vercel,
                "required_env_var": "ULTRON_DATABASE_URL",
            },
        )

    if lower.startswith("sqlite"):
        if not allow_sqlite:
            raise DatabaseConfigurationError(
                "SQLite is not permitted in deployed environments (production, staging, or Vercel deployments). "
                "Configure ULTRON_DATABASE_URL with a Supabase PostgreSQL connection string.",
                details={
                    "env": env_label,
                    "vercel": is_vercel,
                    "required_env_var": "ULTRON_DATABASE_URL",
                },
            )
        try:
            parsed = make_url(cleaned)
        except Exception as exc:
            raise DatabaseConfigurationError(
                "ULTRON_DATABASE_URL is not a valid SQLite connection string.",
                details={"required_env_var": "ULTRON_DATABASE_URL"},
            ) from exc
        return parsed.render_as_string(hide_password=False)

    # Normalize standard PostgreSQL schemes to the installed psycopg v3 driver.
    candidate = cleaned
    if lower.startswith("postgres://"):
        candidate = "postgresql+psycopg://" + cleaned[len("postgres://") :]
    elif lower.startswith("postgresql://"):
        candidate = "postgresql+psycopg://" + cleaned[len("postgresql://") :]
    elif lower.startswith("postgresql+psycopg2://"):
        candidate = "postgresql+psycopg://" + cleaned[len("postgresql+psycopg2://") :]
    elif not lower.startswith("postgresql+"):
        raise DatabaseConfigurationError(
            "Unsupported database scheme in ULTRON_DATABASE_URL. Use a PostgreSQL connection string (postgresql://...).",
            details={
                "env": env_label,
                "vercel": is_vercel,
                "required_env_var": "ULTRON_DATABASE_URL",
            },
        )

    candidate = _encode_unencoded_pg_password(candidate)

    try:
        parsed = make_url(candidate)
    except Exception as exc:
        raise DatabaseConfigurationError(
            "ULTRON_DATABASE_URL could not be parsed as a valid PostgreSQL connection string. "
            "Verify URL encoding of special characters in the database password.",
            details={"required_env_var": "ULTRON_DATABASE_URL"},
        ) from exc

    if not parsed.host:
        raise DatabaseConfigurationError(
            "ULTRON_DATABASE_URL is missing a PostgreSQL hostname.",
            details={"required_env_var": "ULTRON_DATABASE_URL"},
        )

    # Strip non-libpq query parameters (e.g. ?pgbouncer=true, ?supa=base-pooler.x)
    # that Supabase/Prisma URLs often include but psycopg v3/libpq rejects at connect time.
    if parsed.query:
        filtered_query = {
            k: v for k, v in parsed.query.items() if k.strip().lower() not in _NON_LIBPQ_QUERY_PARAMS
        }
        parsed = parsed.set(query=filtered_query)

    host_lower = parsed.host.strip().lower()
    if host_lower not in _LOCAL_PG_HOSTS and "sslmode" not in parsed.query:
        parsed = parsed.update_query_dict({"sslmode": "require"})

    # Validate final libpq URI parameters with psycopg v3 if installed (never echoing secrets).
    try:
        import psycopg.conninfo

        libpq_url = parsed.set(drivername="postgresql").render_as_string(hide_password=False)
        psycopg.conninfo.conninfo_to_dict(libpq_url)
    except ImportError:
        pass
    except Exception as exc:
        raise DatabaseConfigurationError(
            "ULTRON_DATABASE_URL contains an unsupported PostgreSQL URI parameter or syntax error. "
            "Remove unsupported query parameters and verify URL encoding of the password.",
            details={"required_env_var": "ULTRON_DATABASE_URL", "reason": type(exc).__name__},
        ) from exc

    return parsed.render_as_string(hide_password=False)


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
    vercel: str = Field(default="", alias="VERCEL")
    vercel_env: str = Field(default="", alias="VERCEL_ENV")
    vercel_url: str = Field(default="", alias="VERCEL_URL")
    vercel_branch_url: str = Field(default="", alias="VERCEL_BRANCH_URL")
    app_name: str = Field(default="ULTRON OS 2026 Backend", alias="ULTRON_APP_NAME")
    app_version: str = Field(default="2026.4.0", alias="ULTRON_APP_VERSION")
    host: str = Field(default="127.0.0.1", alias="ULTRON_HOST")
    port: int = Field(default=8000, alias="ULTRON_PORT")
    log_level: str = Field(default="INFO", alias="ULTRON_LOG_LEVEL")
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        alias="ULTRON_CORS_ORIGINS",
    )

    # --- Rate Limiting & Orchestration Limits ---
    rate_limit_requests_per_minute: int = Field(
        default=180, ge=10, le=10000, alias="ULTRON_RATE_LIMIT_PER_MIN"
    )
    redis_rest_url: str = Field(default="", alias="ULTRON_REDIS_REST_URL")
    redis_rest_token: SecretStr | None = Field(default=None, alias="ULTRON_REDIS_REST_TOKEN")
    argon_max_parallel_steps: int = Field(default=4, ge=1, le=32, alias="ULTRON_ARGON_MAX_PARALLEL_STEPS")
    argon_default_step_retries: int = Field(default=1, ge=0, le=5, alias="ULTRON_ARGON_DEFAULT_STEP_RETRIES")
    argon_step_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0, alias="ULTRON_ARGON_STEP_TIMEOUT_SECONDS")

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
    database_url: str = Field(default="", validation_alias=AliasChoices("ULTRON_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL", "SUPABASE_DATABASE_URL", "POSTGRES_PRISMA_URL"))
    sqlite_path: str = Field(default="./data/ultron_os_2026.db", alias="ULTRON_SQLITE_PATH")
    db_pool_size: int = Field(default=10, ge=1, le=100, alias="ULTRON_DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, ge=0, le=100, alias="ULTRON_DB_MAX_OVERFLOW")
    auto_init_schema: bool = Field(default=True, alias="ULTRON_AUTO_INIT_SCHEMA")

    # --- Supabase ---
    supabase_url: str = Field(default="", validation_alias=AliasChoices("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL"))
    supabase_anon_key: SecretStr | None = Field(default=None, validation_alias=AliasChoices("SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_ANON_KEY"))
    supabase_service_role_key: SecretStr | None = Field(default=None, validation_alias=AliasChoices("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"))
    supabase_storage_bucket: str = Field(default="ultron-private-files", alias="SUPABASE_STORAGE_BUCKET")

    # --- Multi-Model LLM Providers (Official Nov 2026 Gemini Models Primary + Optional Failover) ---
    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        alias="GEMINI_BASE_URL",
    )
    gemini_api_mode: Literal["generate_content", "interactions", "auto"] = Field(
        default="generate_content",
        alias="GEMINI_API_MODE",
    )
    gemini_interactions_store: bool = Field(
        default=False,
        alias="GEMINI_INTERACTIONS_STORE",
    )
    gemini_request_timeout_seconds: float = Field(
        default=25.0,
        ge=3.0,
        le=120.0,
        alias="GEMINI_REQUEST_TIMEOUT_SECONDS",
    )
    gemini_max_retries: int = Field(
        default=1,
        ge=0,
        le=4,
        alias="GEMINI_MAX_RETRIES",
    )
    # Legacy 3-band defaults preserved for full backwards compatibility
    gemini_model_fast: str = Field(default="gemini-3.5-flash-lite", alias="GEMINI_MODEL_FAST")
    gemini_model_standard: str = Field(default="gemini-3.8-flash", alias="GEMINI_MODEL_STANDARD")
    gemini_model_reasoning: str = Field(default="gemini-4-argon", alias="GEMINI_MODEL_REASONING")
    gemini_model_embedding: str = Field(default="gemini-embedding-001", alias="GEMINI_MODEL_EMBEDDING")
    gemini_model_image: str = Field(default="gemini-nano-banana-2.1", alias="GEMINI_MODEL_IMAGE")
    # Explicit 5-Tier configurable overrides (Tier 1..5). Empty string falls back to verified defaults.
    gemini_model_tier_1: str = Field(default="", alias="GEMINI_MODEL_TIER_1")
    gemini_model_tier_2: str = Field(default="", alias="GEMINI_MODEL_TIER_2")
    gemini_model_tier_3: str = Field(default="", alias="GEMINI_MODEL_TIER_3")
    gemini_model_tier_4: str = Field(default="", alias="GEMINI_MODEL_TIER_4")
    gemini_model_tier_5: str = Field(default="", alias="GEMINI_MODEL_TIER_5")

    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model_fallback: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL_FALLBACK")

    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_base_url: str = Field(default="https://api.anthropic.com/v1", alias="ANTHROPIC_BASE_URL")
    anthropic_model_fallback: str = Field(default="claude-3-5-sonnet-latest", alias="ANTHROPIC_MODEL_FALLBACK")

    ollama_base_url: str = Field(default="", alias="OLLAMA_BASE_URL")
    ollama_model_local: str = Field(default="llama3.2", alias="OLLAMA_MODEL_LOCAL")

    # --- OAuth 2.0 Client Configuration ---
    google_oauth_client_id: str = Field(default="", alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: SecretStr | None = Field(default=None, alias="GOOGLE_OAUTH_CLIENT_SECRET")
    google_oauth_redirect_uri: str = Field(
        default="http://localhost:5173/oauth/callback",
        alias="GOOGLE_OAUTH_REDIRECT_URI",
    )
    github_oauth_client_id: str = Field(default="", alias="GITHUB_OAUTH_CLIENT_ID")
    github_oauth_client_secret: SecretStr | None = Field(default=None, alias="GITHUB_OAUTH_CLIENT_SECRET")
    github_oauth_redirect_uri: str = Field(
        default="http://localhost:5173/oauth/callback",
        alias="GITHUB_OAUTH_REDIRECT_URI",
    )

    # --- Google Ecosystem Service-Specific Tokens & Search ---
    google_drive_access_token: SecretStr | None = Field(default=None, alias="GOOGLE_DRIVE_ACCESS_TOKEN")
    google_gmail_access_token: SecretStr | None = Field(default=None, alias="GOOGLE_GMAIL_ACCESS_TOKEN")
    google_calendar_access_token: SecretStr | None = Field(default=None, alias="GOOGLE_CALENDAR_ACCESS_TOKEN")
    google_docs_access_token: SecretStr | None = Field(default=None, alias="GOOGLE_DOCS_ACCESS_TOKEN")
    google_sheets_access_token: SecretStr | None = Field(default=None, alias="GOOGLE_SHEETS_ACCESS_TOKEN")
    google_slides_access_token: SecretStr | None = Field(default=None, alias="GOOGLE_SLIDES_ACCESS_TOKEN")
    google_cloud_access_token: SecretStr | None = Field(default=None, alias="GOOGLE_CLOUD_ACCESS_TOKEN")
    google_cloud_project_id: str = Field(default="", alias="GOOGLE_CLOUD_PROJECT_ID")
    google_search_api_key: SecretStr | None = Field(default=None, alias="GOOGLE_SEARCH_API_KEY")
    google_search_cx: str = Field(default="", alias="GOOGLE_SEARCH_CX")

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

    # --- Extended Tool Integrations ---
    github_token: SecretStr | None = Field(default=None, alias="GITHUB_TOKEN")
    github_default_repo: str = Field(default="epejuwon-sketch/ULTRON", alias="GITHUB_DEFAULT_REPO")
    email_smtp_host: str = Field(default="", alias="EMAIL_SMTP_HOST")
    email_api_key: SecretStr | None = Field(default=None, alias="EMAIL_API_KEY")
    whatsapp_access_token: SecretStr | None = Field(default=None, alias="WHATSAPP_ACCESS_TOKEN")
    whatsapp_phone_number_id: str = Field(default="", alias="WHATSAPP_PHONE_NUMBER_ID")
    payment_provider_key: SecretStr | None = Field(default=None, alias="PAYMENT_PROVIDER_KEY")

    # UBA Verve Direct Integration (Developer Zone)
    uba_api_base_url: str = Field(default="", alias="UBA_API_BASE_URL")
    uba_client_id: str = Field(default="", alias="UBA_CLIENT_ID")
    uba_client_secret: SecretStr | None = Field(default=None, alias="UBA_CLIENT_SECRET")
    uba_api_key: SecretStr | None = Field(default=None, alias="UBA_API_KEY")
    uba_environment: Literal["sandbox", "production"] = Field(default="sandbox", alias="UBA_ENVIRONMENT")

    # Flutterwave Sandbox Integration (Hosted Checkout)
    flw_public_key: str = Field(default="", alias="FLW_PUBLIC_KEY")
    flw_secret_key: SecretStr | None = Field(default=None, alias="FLW_SECRET_KEY")
    flw_encryption_key: SecretStr | None = Field(default=None, alias="FLW_ENCRYPTION_KEY")
    flw_secret_hash: SecretStr | None = Field(default=None, alias="FLW_SECRET_HASH")
    flw_environment: Literal["test", "live"] = Field(default="test", alias="FLW_ENVIRONMENT")

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
    def is_vercel(self) -> bool:
        """True when running inside a Vercel preview or production serverless deployment."""
        vercel_env = self.vercel_env.strip().lower()
        if vercel_env in {"production", "preview"}:
            return True
        return self.vercel.strip().lower() in {"1", "true", "yes"} and vercel_env != "development"

    @property
    def is_deployed_environment(self) -> bool:
        """True in production, staging, or Vercel deployments where SQLite fallback is prohibited."""
        return self.ultron_env in {"production", "staging"} or self.is_vercel

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        for host in (self.vercel_url.strip(), self.vercel_branch_url.strip()):
            if not host:
                continue
            origin = host if host.startswith(("http://", "https://")) else f"https://{host}"
            if origin not in origins:
                origins.append(origin)
        return origins

    @property
    def effective_database_url(self) -> str:
        """Return the normalized SQLAlchemy database URL.

        In deployed environments (production, staging, Vercel), ULTRON_DATABASE_URL
        must be a valid PostgreSQL connection string; SQLite fallback is strictly disabled.
        In local development and automated tests, an empty ULTRON_DATABASE_URL uses SQLite.
        """
        normalized = normalize_database_url(
            self.database_url,
            allow_sqlite=not self.is_deployed_environment,
            env_label=self.ultron_env,
            is_vercel=self.is_vercel,
        )
        if normalized:
            return normalized
        return f"sqlite:///{self.sqlite_path}"

    @property
    def database_backend(self) -> str:
        """Return active database backend label without raising or exposing credentials."""
        raw = _strip_matching_quotes(self.database_url).lower()
        if not raw:
            return "unconfigured" if self.is_deployed_environment else "sqlite"
        if raw.startswith("postgresql") or raw.startswith("postgres://"):
            return "postgresql"
        if raw.startswith("sqlite"):
            return "unconfigured" if self.is_deployed_environment else "sqlite"
        return "invalid"

    def database_diagnostics(self) -> dict[str, Any]:
        """Return strictly non-secret database connection metadata for readiness diagnostics."""
        backend = self.database_backend
        pool_strategy = (
            "sqlite_local"
            if backend == "sqlite"
            else ("null_pool_serverless" if self.is_vercel else "queue_pool")
        )
        info: dict[str, Any] = {
            "uses_pooler": False,
            "port": None,
            "sslmode_enforced": False,
            "pool_strategy": pool_strategy,
            "password_wrapped_in_brackets": False,
        }
        if backend != "postgresql":
            return info
        try:
            normalized = self.effective_database_url
            parsed = make_url(normalized)
            host_lower = (parsed.host or "").lower()
            raw_lower = self.database_url.lower()
            info["port"] = parsed.port or 5432
            info["uses_pooler"] = (
                parsed.port == 6543
                or "pooler.supabase" in host_lower
                or "pgbouncer=" in raw_lower
                or "supa=" in raw_lower
            )
            info["sslmode_enforced"] = str(parsed.query.get("sslmode", "")).lower() in {
                "require",
                "verify-ca",
                "verify-full",
            }
            pwd = parsed.password or ""
            info["password_wrapped_in_brackets"] = len(pwd) >= 3 and pwd.startswith("[") and pwd.endswith("]")
        except Exception:
            pass
        return info

    def resolve_gemini_tier_model(self, tier: int) -> str:
        """Resolve the primary verified Gemini model ID for reasoning tiers 1..5."""
        t = max(1, min(5, int(tier)))
        explicit = {
            1: self.gemini_model_tier_1.strip(),
            2: self.gemini_model_tier_2.strip(),
            3: self.gemini_model_tier_3.strip(),
            4: self.gemini_model_tier_4.strip(),
            5: self.gemini_model_tier_5.strip(),
        }[t]
        if explicit:
            return explicit
        if t == 1:
            return self.gemini_model_fast.strip() or "gemini-3.5-flash-lite"
        if t in (2, 3):
            return self.gemini_model_standard.strip() or "gemini-3.8-flash"
        if t == 4:
            # Tier 4 defaults to Gemini 4 Hydrogen (free+paid Gemini 4 reasoning) unless reasoning was custom-overridden
            if self.gemini_model_reasoning.strip() and self.gemini_model_reasoning.strip() != "gemini-4-argon":
                return self.gemini_model_reasoning.strip()
            return "gemini-4-hydrogen"
        # Tier 5 defaults to flagship Gemini 4 Carbon (highest available reasoning) unless custom-overridden
        if self.gemini_model_reasoning.strip() and self.gemini_model_reasoning.strip() != "gemini-4-argon":
            return self.gemini_model_reasoning.strip()
        return "gemini-4-argon"

    def safe_summary(self) -> dict[str, Any]:
        """Return non-sensitive runtime configuration metadata safe for diagnostics."""
        return {
            "env": self.ultron_env,
            "deployed_environment": self.is_deployed_environment,
            "vercel_serverless": self.is_vercel,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "database_backend": self.database_backend,
            "approval_soft_limit_usd": self.approval_soft_limit_usd,
            "default_tenant_id": self.default_tenant_id,
            "rate_limit_per_min": self.rate_limit_requests_per_minute,
            "argon_max_parallel_steps": self.argon_max_parallel_steps,
            "gemini_api_mode": self.gemini_api_mode,
            "gemini_models": {
                "fast": self.gemini_model_fast,
                "standard": self.gemini_model_standard,
                "reasoning": self.gemini_model_reasoning,
                "embedding": self.gemini_model_embedding,
                "image": self.gemini_model_image,
            },
            "gemini_tier_models": {f"tier_{t}": self.resolve_gemini_tier_model(t) for t in range(1, 6)},
            "integrations_configured": {
                "supabase": bool(self.supabase_url.strip() and (self.supabase_service_role_key or self.supabase_anon_key)),
                "gemini": bool(self.gemini_api_key and self.gemini_api_key.get_secret_value().strip()),
                "openai": bool(self.openai_api_key and self.openai_api_key.get_secret_value().strip()),
                "anthropic": bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value().strip()),
                "ollama": bool(self.ollama_base_url.strip()),
                "vercel": bool(self.vercel_token and self.vercel_token.get_secret_value().strip()),
                "cloudflare": bool(self.cloudflare_api_token and self.cloudflare_api_token.get_secret_value().strip()),
                "github": bool(self.github_token and self.github_token.get_secret_value().strip()),
                "google_oauth": bool(self.google_oauth_client_id.strip() and self.google_oauth_client_secret),
                "google_drive": bool(self.google_drive_access_token and self.google_drive_access_token.get_secret_value().strip()),
                "google_gmail": bool(self.google_gmail_access_token and self.google_gmail_access_token.get_secret_value().strip()),
                "google_calendar": bool(self.google_calendar_access_token and self.google_calendar_access_token.get_secret_value().strip()),
                "google_docs": bool(self.google_docs_access_token and self.google_docs_access_token.get_secret_value().strip()),
                "google_sheets": bool(self.google_sheets_access_token and self.google_sheets_access_token.get_secret_value().strip()),
                "google_slides": bool(self.google_slides_access_token and self.google_slides_access_token.get_secret_value().strip()),
                "google_cloud": bool(self.google_cloud_access_token and self.google_cloud_access_token.get_secret_value().strip()),
                "google_search": bool(self.google_search_api_key and self.google_search_cx.strip()),
            },
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor; call `get_settings.cache_clear()` in tests after env overrides."""
    return Settings()
