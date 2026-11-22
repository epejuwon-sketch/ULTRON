"""Google Gemini API client (Nov 2026 official models: discovery, generation, multimodal, function calling, streaming, and embeddings)."""

from __future__ import annotations

import json
import time
from collections.abc import Generator
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import IntegrationError
from app.integrations.base import HonestCapabilityState, IntegrationStatus, classify_http_error


class GeminiClient:
    """Direct REST client for the Google Gemini API (`generativelanguage.googleapis.com`).

    Passes the API key strictly via `x-goog-api-key` header (never in URL query parameters).
    Supports dynamic model discovery, native function calling, structured JSON outputs,
    multimodal inline parts, SSE streaming, retry/backoff on 429/5xx, and embeddings.
    """

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None, api_key_override: str | None = None) -> None:
        self._settings = settings
        self._client = http_client
        self._api_key_override = api_key_override

    @property
    def base_url(self) -> str:
        return self._settings.gemini_base_url.strip().rstrip("/")

    @property
    def _api_key(self) -> str:
        if self._api_key_override:
            return self._api_key_override.strip()
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

    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout_seconds: float = 20.0,
        max_retries: int = 2,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                if self._client is not None:
                    resp = self._client.request(method, url, headers=self._headers(), params=params, json=json_body, timeout=timeout_seconds)
                else:
                    with httpx.Client(timeout=timeout_seconds) as client:
                        resp = client.request(method, url, headers=self._headers(), params=params, json=json_body)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                    time.sleep(min(0.25 * (2**attempt), 2.0))
                    continue
                return resp
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < max_retries:
                    time.sleep(min(0.25 * (2**attempt), 2.0))
                    continue
        raise IntegrationError(f"Gemini request failed after retries: {type(last_exc).__name__}") from last_exc

    def status_without_network(self) -> IntegrationStatus:
        missing = self.missing_env_vars()
        if missing:
            return IntegrationStatus(
                provider="gemini",
                configured=False,
                capability_state=HonestCapabilityState.DEFINED_NOT_INSTALLED,
                live_verified=False,
                missing_env_vars=missing,
                detail="GEMINI_API_KEY not configured; NEON router runs in deterministic offline mode.",
            )
        return IntegrationStatus(
            provider="gemini",
            configured=True,
            capability_state=HonestCapabilityState.INSTALLED,
            live_verified=False,
            endpoint=f"{self.base_url}/models",
            detail="GEMINI_API_KEY present; run live verification to discover live models.",
        )

    def list_models(self, *, page_size: int = 50, timeout_seconds: float = 8.0) -> list[dict[str, Any]]:
        """Discover currently supported models directly from the live Gemini API."""
        if not self.is_configured():
            raise IntegrationError("GEMINI_API_KEY is not configured.", details={"missing": ["GEMINI_API_KEY"]})
        endpoint = f"{self.base_url}/models"
        resp = self._request_with_retry("GET", endpoint, params={"pageSize": page_size}, timeout_seconds=timeout_seconds, max_retries=1)
        if resp.status_code >= 400:
            raise IntegrationError(f"Gemini model discovery failed: {classify_http_error(resp.status_code)}")
        raw_models = resp.json().get("models", [])
        return [
            {
                "id": str(m.get("name", "")).removeprefix("models/"),
                "display_name": m.get("displayName", ""),
                "supported_methods": m.get("supportedGenerationMethods", []),
                "input_token_limit": m.get("inputTokenLimit"),
                "output_token_limit": m.get("outputTokenLimit"),
            }
            for m in raw_models
        ]

    def verify_live(self, timeout_seconds: float = 8.0) -> IntegrationStatus:
        if not self.is_configured():
            return self.status_without_network()

        endpoint = f"{self.base_url}/models"
        started = time.perf_counter()
        try:
            resp = self._request_with_retry("GET", endpoint, params={"pageSize": 20}, timeout_seconds=timeout_seconds, max_retries=0)
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
                    detail=f"Gemini API live check passed ({len(models)} models discovered).",
                )
            return IntegrationStatus(
                provider="gemini",
                configured=True,
                capability_state=HonestCapabilityState.DEGRADED,
                live_verified=False,
                endpoint=endpoint,
                latency_ms=latency_ms,
                detail=classify_http_error(resp.status_code),
            )
        except IntegrationError as exc:
            return IntegrationStatus(
                provider="gemini",
                configured=True,
                capability_state=HonestCapabilityState.UNAVAILABLE,
                live_verified=False,
                endpoint=endpoint,
                detail=str(exc),
            )

    def generate_content(
        self,
        *,
        prompt: str,
        system_instruction: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        response_mime_type: str | None = None,
        function_declarations: list[dict[str, Any]] | None = None,
        multimodal_parts: list[dict[str, Any]] | None = None,
        timeout_seconds: float = 20.0,
    ) -> dict[str, Any]:
        """Call Gemini `generateContent` supporting multimodal parts, structured JSON, and function calling."""
        if not self.is_configured():
            raise IntegrationError("GEMINI_API_KEY is not configured.", details={"missing": ["GEMINI_API_KEY"]})

        target_model = model or self._settings.gemini_model_standard
        endpoint = f"{self.base_url}/models/{target_model}:generateContent"

        parts: list[dict[str, Any]] = [{"text": prompt}]
        if multimodal_parts:
            parts.extend(multimodal_parts)

        gen_cfg: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        }
        if response_mime_type:
            gen_cfg["responseMimeType"] = response_mime_type

        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": gen_cfg,
        }
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if function_declarations:
            body["tools"] = [{"functionDeclarations": function_declarations}]

        started = time.perf_counter()
        resp = self._request_with_retry("POST", endpoint, json_body=body, timeout_seconds=timeout_seconds)
        latency_ms = int((time.perf_counter() - started) * 1000)

        if resp.status_code >= 400:
            raise IntegrationError(
                f"Gemini generateContent failed: {classify_http_error(resp.status_code)}",
                details={"status_code": resp.status_code, "model": target_model},
            )

        data = resp.json()
        candidates = data.get("candidates", [])
        text_parts: list[str] = []
        function_calls: list[dict[str, Any]] = []
        if candidates:
            for part in candidates[0].get("content", {}).get("parts", []):
                if "text" in part:
                    text_parts.append(part["text"])
                if "functionCall" in part:
                    function_calls.append(part["functionCall"])

        usage = data.get("usageMetadata", {})
        return {
            "provider": "gemini",
            "model": target_model,
            "text": "\n".join(text_parts).strip(),
            "function_calls": function_calls,
            "latency_ms": latency_ms,
            "usage": {
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "total_tokens": usage.get("totalTokenCount", 0),
            },
        }

    def stream_generate_content(
        self,
        *,
        prompt: str,
        system_instruction: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        timeout_seconds: float = 30.0,
    ) -> Generator[str, None, None]:
        """Stream live text deltas via Gemini `streamGenerateContent?alt=sse`."""
        if not self.is_configured():
            raise IntegrationError("GEMINI_API_KEY is not configured.")
        target_model = model or self._settings.gemini_model_standard
        endpoint = f"{self.base_url}/models/{target_model}:streamGenerateContent"
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_output_tokens},
        }
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        with httpx.Client(timeout=timeout_seconds) as client:
            with client.stream("POST", endpoint, headers=self._headers(), params={"alt": "sse"}, json=body) as resp:
                if resp.status_code >= 400:
                    raise IntegrationError(f"Gemini stream failed: {classify_http_error(resp.status_code)}")
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line.removeprefix("data:").strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    for cand in chunk.get("candidates", []):
                        for part in cand.get("content", {}).get("parts", []):
                            if "text" in part:
                                yield part["text"]

    def embed_text(
        self,
        text: str,
        *,
        model: str | None = None,
        output_dimensionality: int = 768,
        timeout_seconds: float = 10.0,
    ) -> list[float]:
        """Generate a semantic embedding vector via Gemini `embedContent` (`gemini-embedding-001` / `gemini-embedding-2`)."""
        if not self.is_configured():
            raise IntegrationError("GEMINI_API_KEY is not configured.", details={"missing": ["GEMINI_API_KEY"]})

        target_model = model or self._settings.gemini_model_embedding
        endpoint = f"{self.base_url}/models/{target_model}:embedContent"
        body: dict[str, Any] = {
            "model": f"models/{target_model}",
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": output_dimensionality,
        }
        resp = self._request_with_retry("POST", endpoint, json_body=body, timeout_seconds=timeout_seconds, max_retries=1)
        if resp.status_code >= 400:
            raise IntegrationError(f"Gemini embedContent failed: {classify_http_error(resp.status_code)}")
        values = resp.json().get("embedding", {}).get("values", [])
        return [float(v) for v in values]
