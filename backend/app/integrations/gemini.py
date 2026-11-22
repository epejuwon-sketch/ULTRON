"""Google Gemini API client (content generation, embeddings, and honest live verification)."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import IntegrationError
from app.integrations.base import HonestCapabilityState, IntegrationStatus, classify_http_error


class GeminiClient:
    """Direct REST client for the Google Gemini API (`generativelanguage.googleapis.com`).

    Passes the API key via `x-goog-api-key` header (never in URL query parameters)
    to prevent accidental credential leakage in proxy or access logs.
    """

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = http_client

    @property
    def base_url(self) -> str:
        return self._settings.gemini_base_url.strip().rstrip("/")

    @property
    def _api_key(self) -> str:
        if self._settings.gemini_api_key:
            return self._settings.gemini_api_key.get_secret_value().strip()
        return ""

    def missing_env_vars(self) -> list[str]:
        return [] if self._api_key else ["GEMINI_API_KEY"]

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }

    def status_without_network(self) -> IntegrationStatus:
        missing = self.missing_env_vars()
        if missing:
            return IntegrationStatus(
                provider="gemini",
                configured=False,
                capability_state=HonestCapabilityState.DEFINED_NOT_INSTALLED,
                live_verified=False,
                missing_env_vars=missing,
                detail="GEMINI_API_KEY not configured; NEON router will run in deterministic local planning mode.",
            )
        return IntegrationStatus(
            provider="gemini",
            configured=True,
            capability_state=HonestCapabilityState.INSTALLED,
            live_verified=False,
            endpoint=f"{self.base_url}/models",
            detail="GEMINI_API_KEY present; run live verification to confirm API access.",
        )

    def verify_live(self, timeout_seconds: float = 8.0) -> IntegrationStatus:
        if not self.is_configured():
            return self.status_without_network()

        endpoint = f"{self.base_url}/models"
        started = time.perf_counter()
        try:
            if self._client is not None:
                resp = self._client.get(endpoint, headers=self._headers(), params={"pageSize": 5}, timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.get(endpoint, headers=self._headers(), params={"pageSize": 5})
            latency_ms = int((time.perf_counter() - started) * 1000)
            if 200 <= resp.status_code < 300:
                models = resp.json().get("models", [])
                return IntegrationStatus(
                    provider="gemini",
                    configured=True,
                    capability_state=HonestCapabilityState.AVAILABLE,
                    live_verified=True,
                    endpoint=endpoint,
                    latency_ms=latency_ms,
                    detail=f"Gemini API live check passed ({len(models)} models returned in page).",
                )
            return IntegrationStatus(
                provider="gemini",
                configured=True,
                capability_state=HonestCapabilityState.INSTALLED,
                live_verified=False,
                endpoint=endpoint,
                latency_ms=latency_ms,
                detail=classify_http_error(resp.status_code),
            )
        except httpx.TimeoutException:
            return IntegrationStatus(
                provider="gemini",
                configured=True,
                capability_state=HonestCapabilityState.INSTALLED,
                live_verified=False,
                endpoint=endpoint,
                detail="PROVIDER_TIMEOUT: Gemini API timed out.",
            )
        except httpx.HTTPError as exc:
            return IntegrationStatus(
                provider="gemini",
                configured=True,
                capability_state=HonestCapabilityState.INSTALLED,
                live_verified=False,
                endpoint=endpoint,
                detail=f"PROVIDER_NETWORK_UNAVAILABLE: {type(exc).__name__}",
            )

    def generate_content(
        self,
        *,
        prompt: str,
        system_instruction: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        timeout_seconds: float = 20.0,
    ) -> dict[str, Any]:
        """Call Gemini `generateContent` endpoint and return normalized response metadata."""
        if not self.is_configured():
            raise IntegrationError("GEMINI_API_KEY is not configured.", details={"missing": ["GEMINI_API_KEY"]})

        target_model = model or self._settings.gemini_model_standard
        endpoint = f"{self.base_url}/models/{target_model}:generateContent"
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        started = time.perf_counter()
        try:
            if self._client is not None:
                resp = self._client.post(endpoint, headers=self._headers(), json=body, timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.post(endpoint, headers=self._headers(), json=body)
        except httpx.TimeoutException as exc:
            raise IntegrationError("Gemini generateContent timed out.") from exc
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Gemini network error: {type(exc).__name__}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if resp.status_code >= 400:
            raise IntegrationError(
                f"Gemini generateContent failed: {classify_http_error(resp.status_code)}",
                details={"status_code": resp.status_code, "model": target_model},
            )

        data = resp.json()
        candidates = data.get("candidates", [])
        text_parts: list[str] = []
        if candidates:
            for part in candidates[0].get("content", {}).get("parts", []):
                if "text" in part:
                    text_parts.append(part["text"])

        usage = data.get("usageMetadata", {})
        return {
            "provider": "gemini",
            "model": target_model,
            "text": "\n".join(text_parts).strip(),
            "latency_ms": latency_ms,
            "usage": {
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", 0),
            },
        }

    def embed_text(self, text: str, *, model: str | None = None, timeout_seconds: float = 10.0) -> list[float]:
        """Generate a semantic embedding vector via Gemini `embedContent`."""
        if not self.is_configured():
            raise IntegrationError("GEMINI_API_KEY is not configured.", details={"missing": ["GEMINI_API_KEY"]})

        target_model = model or self._settings.gemini_model_embedding
        endpoint = f"{self.base_url}/models/{target_model}:embedContent"
        body = {
            "model": f"models/{target_model}",
            "content": {"parts": [{"text": text}]},
        }
        try:
            if self._client is not None:
                resp = self._client.post(endpoint, headers=self._headers(), json=body, timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.post(endpoint, headers=self._headers(), json=body)
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Gemini embedContent failed: {type(exc).__name__}") from exc

        if resp.status_code >= 400:
            raise IntegrationError(f"Gemini embedContent failed: {classify_http_error(resp.status_code)}")
        values = resp.json().get("embedding", {}).get("values", [])
        return [float(v) for v in values]
