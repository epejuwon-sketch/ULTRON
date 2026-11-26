"""OAuth 2.0 + PKCE (S256) engine with least-privilege per-service scope catalogs."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.core.exceptions import IntegrationError, ValidationError


@dataclass(frozen=True)
class OAuthProviderSpec:
    provider: str
    family: str  # google | github
    authorize_url: str
    token_url: str
    revoke_url: str | None
    default_scopes: tuple[str, ...]
    mutation_scopes: tuple[str, ...]


# Strictly least-privilege per-service scopes — never assume one token grants every Google product.
OAUTH_PROVIDERS: dict[str, OAuthProviderSpec] = {
    "google_drive": OAuthProviderSpec(
        provider="google_drive",
        family="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        revoke_url="https://oauth2.googleapis.com/revoke",
        default_scopes=("https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive.metadata.readonly"),
        mutation_scopes=("https://www.googleapis.com/auth/drive.file",),
    ),
    "google_gmail": OAuthProviderSpec(
        provider="google_gmail",
        family="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        revoke_url="https://oauth2.googleapis.com/revoke",
        default_scopes=("https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.compose"),
        mutation_scopes=("https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.modify"),
    ),
    "google_calendar": OAuthProviderSpec(
        provider="google_calendar",
        family="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        revoke_url="https://oauth2.googleapis.com/revoke",
        default_scopes=("https://www.googleapis.com/auth/calendar.readonly", "https://www.googleapis.com/auth/calendar.events"),
        mutation_scopes=("https://www.googleapis.com/auth/calendar.events",),
    ),
    "google_docs": OAuthProviderSpec(
        provider="google_docs",
        family="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        revoke_url="https://oauth2.googleapis.com/revoke",
        default_scopes=("https://www.googleapis.com/auth/documents", "https://www.googleapis.com/auth/drive.file"),
        mutation_scopes=("https://www.googleapis.com/auth/documents",),
    ),
    "google_sheets": OAuthProviderSpec(
        provider="google_sheets",
        family="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        revoke_url="https://oauth2.googleapis.com/revoke",
        default_scopes=("https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"),
        mutation_scopes=("https://www.googleapis.com/auth/spreadsheets",),
    ),
    "google_slides": OAuthProviderSpec(
        provider="google_slides",
        family="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        revoke_url="https://oauth2.googleapis.com/revoke",
        default_scopes=("https://www.googleapis.com/auth/presentations", "https://www.googleapis.com/auth/drive.file"),
        mutation_scopes=("https://www.googleapis.com/auth/presentations",),
    ),
    "google_cloud": OAuthProviderSpec(
        provider="google_cloud",
        family="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        revoke_url="https://oauth2.googleapis.com/revoke",
        default_scopes=("https://www.googleapis.com/auth/cloud-platform.read-only",),
        mutation_scopes=("https://www.googleapis.com/auth/cloud-platform",),
    ),
    "github": OAuthProviderSpec(
        provider="github",
        family="github",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        revoke_url=None,
        default_scopes=("read:user", "repo"),
        mutation_scopes=("repo", "workflow"),
    ),
}


def generate_pkce_pair() -> tuple[str, str]:
    """Generate RFC 7636 PKCE verifier and S256 challenge."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def validate_oauth_redirect_uri(redirect_uri: str) -> str:
    from urllib.parse import urlparse

    clean = (redirect_uri or "").strip()
    parsed_r = urlparse(clean)
    if (
        parsed_r.scheme not in {"http", "https"}
        or not parsed_r.netloc
        or parsed_r.path != "/oauth/callback"
        or parsed_r.query
        or parsed_r.fragment
    ):
        raise ValidationError(
            "OAuth redirect_uri must be a valid HTTP(S) URL ending in '/oauth/callback' with no query or fragment."
        )
    return clean


def get_oauth_client_credentials(
    provider: str,
    settings: Settings,
    *,
    vault_creds: tuple[str, str, str] | None = None,
) -> tuple[str, str, str]:
    spec = OAUTH_PROVIDERS.get(provider)
    if spec is None:
        raise ValidationError(f"OAuth 2.0 is not defined for provider '{provider}'.")
    if spec.family == "google":
        cid = settings.google_oauth_client_id.strip()
        csec = settings.google_oauth_client_secret.get_secret_value().strip() if settings.google_oauth_client_secret else ""
        ruri = settings.google_oauth_redirect_uri.strip()
        if (not cid or not csec) and vault_creds:
            cid, csec, vruri = vault_creds
            if vruri:
                ruri = vruri
        if not cid or not csec:
            raise IntegrationError(
                "Google OAuth setup is not yet available. Administrator configuration is required.",
                details={"missing_env_vars": ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"]},
            )
        return cid, csec, ruri

    cid = settings.github_oauth_client_id.strip()
    csec = settings.github_oauth_client_secret.get_secret_value().strip() if settings.github_oauth_client_secret else ""
    ruri = settings.github_oauth_redirect_uri.strip()
    if (not cid or not csec) and vault_creds:
        cid, csec, vruri = vault_creds
        if vruri:
            ruri = vruri
    if not cid or not csec:
        raise IntegrationError(
            "GitHub OAuth setup is not yet available. Administrator configuration is required.",
            details={"missing_env_vars": ["GITHUB_OAUTH_CLIENT_ID", "GITHUB_OAUTH_CLIENT_SECRET"]},
        )
    return cid, csec, ruri


def build_authorization_url(
    *,
    provider: str,
    state_token: str,
    code_challenge: str,
    scopes: list[str] | None,
    redirect_uri: str | None,
    settings: Settings,
    vault_creds: tuple[str, str, str] | None = None,
) -> tuple[str, list[str], str]:
    spec = OAUTH_PROVIDERS.get(provider)
    if spec is None:
        raise ValidationError(f"Unsupported OAuth provider '{provider}'.")
    cid, _csec, default_redirect = get_oauth_client_credentials(provider, settings, vault_creds=vault_creds)
    effective_redirect = validate_oauth_redirect_uri(redirect_uri or default_redirect)
    effective_scopes = scopes if scopes else list(spec.default_scopes)

    params: dict[str, str] = {
        "client_id": cid,
        "redirect_uri": effective_redirect,
        "response_type": "code",
        "scope": " ".join(effective_scopes),
        "state": state_token,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if spec.family == "google":
        params["access_type"] = "offline"
        params["prompt"] = "consent"
        params["include_granted_scopes"] = "false"

    return f"{spec.authorize_url}?{urlencode(params)}", effective_scopes, effective_redirect


def exchange_oauth_code(
    *,
    provider: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    settings: Settings,
    vault_creds: tuple[str, str, str] | None = None,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    spec = OAUTH_PROVIDERS.get(provider)
    if spec is None:
        raise ValidationError(f"Unsupported OAuth provider '{provider}'.")
    cid, csec, _ = get_oauth_client_credentials(provider, settings, vault_creds=vault_creds)
    data = {
        "client_id": cid,
        "client_secret": csec,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    headers = {"Accept": "application/json"}
    try:
        if http_client is not None:
            resp = http_client.post(spec.token_url, data=data, headers=headers, timeout=12.0)
        else:
            with httpx.Client(timeout=12.0) as client:
                resp = client.post(spec.token_url, data=data, headers=headers)
    except httpx.HTTPError as exc:
        raise IntegrationError(f"OAuth token exchange failed: {type(exc).__name__}") from exc

    if resp.status_code >= 400:
        raise IntegrationError(f"OAuth token exchange rejected (HTTP {resp.status_code}).")
    payload = resp.json()
    if "error" in payload or not payload.get("access_token"):
        raise IntegrationError(f"OAuth token exchange error: {payload.get('error', 'missing access_token')}")
    return payload


def refresh_oauth_token(
    *,
    provider: str,
    refresh_token: str,
    settings: Settings,
    vault_creds: tuple[str, str, str] | None = None,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    spec = OAUTH_PROVIDERS.get(provider)
    if spec is None:
        raise ValidationError(f"Unsupported OAuth provider '{provider}'.")
    cid, csec, _ = get_oauth_client_credentials(provider, settings, vault_creds=vault_creds)
    data = {
        "client_id": cid,
        "client_secret": csec,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    headers = {"Accept": "application/json"}
    try:
        if http_client is not None:
            resp = http_client.post(spec.token_url, data=data, headers=headers, timeout=12.0)
        else:
            with httpx.Client(timeout=12.0) as client:
                resp = client.post(spec.token_url, data=data, headers=headers)
    except httpx.HTTPError as exc:
        raise IntegrationError(f"OAuth token refresh failed: {type(exc).__name__}") from exc
    if resp.status_code >= 400:
        raise IntegrationError(f"OAuth refresh rejected (HTTP {resp.status_code}).")
    payload = resp.json()
    if "error" in payload or not payload.get("access_token"):
        raise IntegrationError(f"OAuth refresh error: {payload.get('error', 'missing access_token')}")
    return payload


def revoke_oauth_token(
    *,
    provider: str,
    token: str,
    http_client: httpx.Client | None = None,
) -> bool:
    """Attempt upstream token revocation where supported by the OAuth provider."""
    spec = OAUTH_PROVIDERS.get(provider)
    if spec is None or not spec.revoke_url or not token:
        return False
    try:
        if http_client is not None:
            resp = http_client.post(spec.revoke_url, data={"token": token}, timeout=8.0)
        else:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(spec.revoke_url, data={"token": token})
        return 200 <= resp.status_code < 300
    except httpx.HTTPError:
        return False
