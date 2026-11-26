"""Google Gemini API client (Nov 2026 official models: discovery, generateContent, Interactions API adapter, multimodal, function calling, streaming, and embeddings)."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Generator
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import IntegrationError
from app.core.logging import redact_secrets
from app.integrations.base import HonestCapabilityState, IntegrationStatus, classify_http_error

logger = logging.getLogger("ultron.gemini")

# Known November 2026 deprecation notices from official Google AI Studio documentation
_DEPRECATION_NOTICES: dict[str, str] = {
    "gemini-2.5-pro": "Deprecated Nov 2, 2026; auto-routes to gemini-3.8-flash effective Dec 1, 2026.",
    "gemini-2.5-flash": "Deprecated Nov 2, 2026; auto-routes to gemini-3.5-flash-lite effective Dec 1, 2026.",
    "gemini-embedding-2-preview": "Deprecated Nov 6, 2026; auto-routes to gemini-embedding-2.",
}


def _model_deprecates_sampling_params(model_id: str) -> bool:
    """Gemini 3.5+/4 models deprecate temperature/top_p/top_k and warn of future HTTP 400s."""
    m = (model_id or "").lower()
    return m.startswith(("gemini-3.5", "gemini-3.6", "gemini-3.7", "gemini-3.8", "gemini-4"))


def _infer_model_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize raw Google `/v1beta/models` metadata into actionable capability flags."""
    model_id = str(raw.get("name", "")).removeprefix("models/")
    lower = model_id.lower()
    methods = list(raw.get("supportedGenerationMethods") or [])
    supports_gen = "generateContent" in methods
    supports_stream = "streamGenerateContent" in methods or supports_gen
    supports_embed = "embedContent" in methods

    # Infer modalities conservatively from model family and supported methods
    input_modalities = ["text"]
    output_modalities = ["text"]
    if supports_gen and not lower.startswith("gemma"):
        input_modalities = ["text", "image", "audio", "video", "pdf"]
    if "image" in lower or "nano-banana" in lower or "imagen" in lower:
        output_modalities = ["text", "image"] if supports_gen else ["image"]
    elif "tts" in lower or "live" in lower or "native-audio" in lower:
        output_modalities = ["audio"]
    elif "omni" in lower or "veo" in lower:
        output_modalities = ["text", "image", "video", "audio"]
    elif supports_embed and not supports_gen:
        output_modalities = ["embedding"]

    is_chat_gemini = supports_gen and lower.startswith("gemini-") and "tts" not in lower and "image" not in lower
    supports_interactions = is_chat_gemini and (
        lower.startswith(("gemini-2.5", "gemini-3", "gemini-4", "gemini-omni"))
    )

    return {
        "id": model_id,
        "display_name": raw.get("displayName", model_id),
        "description": str(raw.get("description") or "")[:240],
        "version": raw.get("version", ""),
        "supported_methods": methods,
        "input_token_limit": raw.get("inputTokenLimit"),
        "output_token_limit": raw.get("outputTokenLimit"),
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
        "supports_generate_content": supports_gen,
        "supports_streaming": supports_stream,
        "supports_structured_output": is_chat_gemini,
        "supports_tool_calling": is_chat_gemini,
        "supports_interactions_api": supports_interactions,
        "deprecation_notice": _DEPRECATION_NOTICES.get(model_id),
    }


def _extract_safe_google_error(resp: httpx.Response) -> tuple[str, str]:
    """Extract non-secret Google API `(status_code_name, redacted_message)` from an error response."""
    try:
        payload = resp.json()
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict):
            g_status = str(err.get("status") or "").strip()
            g_msg = redact_secrets(str(err.get("message") or "").strip())[:220]
            return g_status, g_msg
    except Exception:
        pass
    return "", ""


class GeminiClient:
    """Direct REST client for the Google Gemini API (`generativelanguage.googleapis.com`).

    Passes the API key strictly via `x-goog-api-key` header (never in URL query parameters).
    Supports dynamic model discovery, `generateContent` (primary stable path), optional
    Interactions API (`/v1beta/interactions`) behind a non-breaking adapter, native function
    calling, structured JSON outputs, multimodal inline parts, SSE streaming, retry/backoff
    on 429/5xx, and embeddings.
    """

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.Client | None = None,
        api_key_override: str | None = None,
    ) -> None:
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
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> httpx.Response:
        effective_timeout = timeout_seconds if timeout_seconds is not None else self._settings.gemini_request_timeout_seconds
        effective_retries = max_retries if max_retries is not None else self._settings.gemini_max_retries
        last_exc: Exception | None = None
        for attempt in range(effective_retries + 1):
            try:
                if self._client is not None:
                    resp = self._client.request(
                        method,
                        url,
                        headers=self._headers(),
                        params=params,
                        json=json_body,
                        timeout=effective_timeout,
                    )
                else:
                    with httpx.Client(timeout=effective_timeout) as client:
                        resp = client.request(
                            method,
                            url,
                            headers=self._headers(),
                            params=params,
                            json=json_body,
                        )
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < effective_retries:
                    time.sleep(min(0.25 * (2**attempt), 2.0))
                    continue
                return resp
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < effective_retries:
                    time.sleep(min(0.25 * (2**attempt), 2.0))
                    continue
        raise IntegrationError(
            f"Gemini request failed after retries: {type(last_exc).__name__}",
            details={"category": type(last_exc).__name__, "timeout_seconds": effective_timeout},
        ) from last_exc

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
            detail="GEMINI_API_KEY present; run live verification to discover models and verify inference.",
        )

    def list_models(self, *, page_size: int = 100, timeout_seconds: float = 8.0) -> list[dict[str, Any]]:
        """Discover currently supported models and rich metadata directly from the live Gemini API."""
        if not self.is_configured():
            raise IntegrationError("GEMINI_API_KEY is not configured.", details={"missing": ["GEMINI_API_KEY"]})
        endpoint = f"{self.base_url}/models"
        resp = self._request_with_retry(
            "GET",
            endpoint,
            params={"pageSize": page_size},
            timeout_seconds=timeout_seconds,
            max_retries=1,
        )
        if resp.status_code >= 400:
            g_status, g_msg = _extract_safe_google_error(resp)
            suffix = f" ({g_status}: {g_msg})" if g_status or g_msg else ""
            raise IntegrationError(f"Gemini model discovery failed: {classify_http_error(resp.status_code)}{suffix}")
        raw_models = resp.json().get("models", [])
        return [_infer_model_metadata(m) for m in raw_models]

    def verify_live(self, timeout_seconds: float = 8.0) -> IntegrationStatus:
        """Verify live Gemini API credentials & catalogue discovery (distinct from live inference)."""
        if not self.is_configured():
            return self.status_without_network()

        endpoint = f"{self.base_url}/models"
        started = time.perf_counter()
        try:
            resp = self._request_with_retry(
                "GET",
                endpoint,
                params={"pageSize": 50},
                timeout_seconds=timeout_seconds,
                max_retries=0,
            )
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
                    detail=(
                        f"Gemini API catalog check passed ({len(models)} models discovered; "
                        f"run live inference verification to test model execution)."
                    ),
                )
            g_status, g_msg = _extract_safe_google_error(resp)
            extra = f" [{g_status}] {g_msg}" if (g_status or g_msg) else ""
            return IntegrationStatus(
                provider="gemini",
                configured=True,
                capability_state=HonestCapabilityState.DEGRADED,
                live_verified=False,
                endpoint=endpoint,
                latency_ms=latency_ms,
                detail=f"{classify_http_error(resp.status_code)}{extra}",
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

    def generate(
        self,
        *,
        prompt: str,
        system_instruction: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        response_mime_type: str | None = None,
        response_schema: dict[str, Any] | None = None,
        function_declarations: list[dict[str, Any]] | None = None,
        multimodal_parts: list[dict[str, Any]] | None = None,
        timeout_seconds: float | None = None,
        api_mode_override: str | None = None,
    ) -> dict[str, Any]:
        """Unified Gemini inference entry point supporting `generate_content`, `interactions`, or `auto` mode.

        Preserves existing `generateContent` contracts as default and falls back non-destructively
        to `generateContent` if an Interactions API call hits an unsupported schema/endpoint error.
        """
        target_model = model or self._settings.resolve_gemini_tier_model(2)
        mode = (api_mode_override or self._settings.gemini_api_mode or "generate_content").strip().lower()

        use_interactions = False
        if mode == "interactions":
            use_interactions = not multimodal_parts
        elif mode == "auto":
            use_interactions = (
                target_model.startswith("gemini-4")
                and not multimodal_parts
                and not response_mime_type
                and not response_schema
            )

        if use_interactions:
            try:
                return self.create_interaction(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    model=target_model,
                    max_output_tokens=max_output_tokens,
                    response_mime_type=response_mime_type,
                    response_schema=response_schema,
                    function_declarations=function_declarations,
                    timeout_seconds=timeout_seconds,
                )
            except IntegrationError as exc:
                status_code = exc.details.get("status_code") if isinstance(exc.details, dict) else None
                # Do not swallow invalid API key errors; fall back safely on endpoint/schema mismatch (400/404)
                if status_code in (400, 404, 501):
                    logger.info(
                        "Interactions API incompatible for model=%s (HTTP %s); falling back safely to generateContent",
                        target_model,
                        status_code,
                    )
                else:
                    raise

        return self.generate_content(
            prompt=prompt,
            system_instruction=system_instruction,
            model=target_model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type=response_mime_type,
            response_schema=response_schema,
            function_declarations=function_declarations,
            multimodal_parts=multimodal_parts,
            timeout_seconds=timeout_seconds,
        )

    def create_interaction(
        self,
        *,
        prompt: str,
        system_instruction: str | None = None,
        model: str | None = None,
        max_output_tokens: int = 1024,
        response_mime_type: str | None = None,
        response_schema: dict[str, Any] | None = None,
        function_declarations: list[dict[str, Any]] | None = None,
        previous_interaction_id: str | None = None,
        store: bool | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Call Google Gemini Interactions API (`POST /v1beta/interactions`) with stateless tenant-safe defaults."""
        if not self.is_configured():
            raise IntegrationError("GEMINI_API_KEY is not configured.", details={"missing": ["GEMINI_API_KEY"]})

        target_model = model or self._settings.resolve_gemini_tier_model(2)
        endpoint = f"{self.base_url}/interactions"
        effective_max_tokens = (
            max(max_output_tokens, 4096)
            if target_model.startswith(("gemini-4", "gemini-3", "gemini-2.5"))
            else max_output_tokens
        )
        effective_store = self._settings.gemini_interactions_store if store is None else bool(store)

        body: dict[str, Any] = {
            "model": target_model,
            "input": prompt,
            "store": effective_store,
            "generation_config": {
                "max_output_tokens": effective_max_tokens,
            },
        }
        if system_instruction:
            body["system_instruction"] = system_instruction
        if previous_interaction_id:
            body["previous_interaction_id"] = previous_interaction_id
        if response_mime_type:
            resp_fmt: dict[str, Any] = {"type": "text", "mime_type": response_mime_type}
            if response_schema:
                resp_fmt["schema"] = response_schema
            body["response_format"] = resp_fmt
        if function_declarations:
            body["tools"] = [
                {
                    "type": "function",
                    "name": fd["name"],
                    "description": fd.get("description", ""),
                    "parameters": fd.get("parameters", {"type": "object", "properties": {}}),
                }
                for fd in function_declarations
            ]

        started = time.perf_counter()
        resp = self._request_with_retry("POST", endpoint, json_body=body, timeout_seconds=timeout_seconds)
        latency_ms = int((time.perf_counter() - started) * 1000)

        if resp.status_code >= 400:
            category = classify_http_error(resp.status_code)
            g_status, g_msg = _extract_safe_google_error(resp)
            detail_parts = [f"model={target_model}"]
            if g_status:
                detail_parts.append(f"google_status={g_status}")
            if g_msg:
                detail_parts.append(g_msg)
            raise IntegrationError(
                f"Gemini interactions failed: {category} ({'; '.join(detail_parts)})",
                details={
                    "status_code": resp.status_code,
                    "category": category,
                    "google_status": g_status,
                    "model": target_model,
                    "api_interface": "interactions",
                    "safe_detail": g_msg,
                },
            )

        data = resp.json()
        text_parts: list[str] = []
        function_calls: list[dict[str, Any]] = []
        for out in data.get("outputs", []):
            otype = str(out.get("type") or "").lower()
            if otype == "thought":
                continue
            if otype == "text" and out.get("text"):
                text_parts.append(str(out["text"]))
            elif otype in ("function_call", "tool_call"):
                function_calls.append(
                    {
                        "name": out.get("name", ""),
                        "args": out.get("arguments", out.get("args", {})),
                        "call_id": out.get("id"),
                    }
                )

        final_text = "\n".join(text_parts).strip()
        if not final_text and not function_calls:
            raise IntegrationError(
                f"Gemini interactions returned empty visible text (model={target_model})",
                details={
                    "status_code": 200,
                    "category": "EMPTY_MODEL_OUTPUT",
                    "google_status": str(data.get("status") or "EMPTY_OUTPUT"),
                    "model": target_model,
                    "api_interface": "interactions",
                    "safe_detail": "Model returned HTTP 200 without visible text parts.",
                },
            )

        usage = data.get("usage", {})
        pt = int(usage.get("total_input_tokens", usage.get("input_tokens", 0)) or 0)
        ct = int(usage.get("total_output_tokens", usage.get("output_tokens", 0)) or 0)
        tt = int(usage.get("total_tokens", pt + ct) or (pt + ct))
        return {
            "provider": "gemini",
            "api_interface": "interactions",
            "interaction_id": data.get("id"),
            "model": target_model,
            "text": final_text,
            "function_calls": function_calls,
            "latency_ms": latency_ms,
            "usage": {
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "total_tokens": tt,
            },
        }

    def generate_content(
        self,
        *,
        prompt: str,
        system_instruction: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        response_mime_type: str | None = None,
        response_schema: dict[str, Any] | None = None,
        function_declarations: list[dict[str, Any]] | None = None,
        multimodal_parts: list[dict[str, Any]] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Call Gemini `generateContent` supporting multimodal parts, structured JSON, and function calling."""
        if not self.is_configured():
            raise IntegrationError("GEMINI_API_KEY is not configured.", details={"missing": ["GEMINI_API_KEY"]})

        target_model = model or self._settings.resolve_gemini_tier_model(2)
        endpoint = f"{self.base_url}/models/{target_model}:generateContent"

        parts: list[dict[str, Any]] = [{"text": prompt}]
        if multimodal_parts:
            parts.extend(multimodal_parts)

        # Gemini 2.5/3.x/4 thinking models include thinking tokens inside maxOutputTokens; ensure 4096 headroom for visible text.
        effective_max_tokens = (
            max(max_output_tokens, 4096)
            if target_model.startswith(("gemini-4", "gemini-3", "gemini-2.5"))
            else max_output_tokens
        )
        gen_cfg: dict[str, Any] = {
            "maxOutputTokens": effective_max_tokens,
        }
        # Omit deprecated sampling params on Gemini 3.5+/4 models per Google Nov 2026 migration guide
        if not _model_deprecates_sampling_params(target_model):
            gen_cfg["temperature"] = temperature
        if response_mime_type:
            gen_cfg["responseMimeType"] = response_mime_type
        if response_schema:
            gen_cfg["responseSchema"] = response_schema

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
            category = classify_http_error(resp.status_code)
            g_status, g_msg = _extract_safe_google_error(resp)
            logger.warning(
                "Gemini generateContent failed: model=%s http_status=%s category=%s google_status=%s latency_ms=%d detail=%s",
                target_model,
                resp.status_code,
                category,
                g_status or "UNKNOWN",
                latency_ms,
                g_msg or "none",
            )
            detail_parts = [f"model={target_model}"]
            if g_status:
                detail_parts.append(f"google_status={g_status}")
            if g_msg:
                detail_parts.append(g_msg)
            raise IntegrationError(
                f"Gemini generateContent failed: {category} ({'; '.join(detail_parts)})",
                details={
                    "status_code": resp.status_code,
                    "category": category,
                    "google_status": g_status,
                    "model": target_model,
                    "api_interface": "generate_content",
                    "safe_detail": g_msg,
                },
            )

        data = resp.json()
        candidates = data.get("candidates", [])
        text_parts: list[str] = []
        function_calls: list[dict[str, Any]] = []
        finish_reason = ""
        thought_parts_count = 0
        if candidates:
            finish_reason = str(candidates[0].get("finishReason") or "")
            for part in candidates[0].get("content", {}).get("parts", []):
                if part.get("thought") is True:
                    thought_parts_count += 1
                    continue
                if "text" in part and part["text"] is not None:
                    text_parts.append(str(part["text"]))
                if "functionCall" in part:
                    function_calls.append(part["functionCall"])

        final_text = "\n".join(text_parts).strip()
        usage = data.get("usageMetadata", {})
        thoughts_tokens = int(usage.get("thoughtsTokenCount", 0) or 0)

        if not final_text and not function_calls:
            block_reason = str(data.get("promptFeedback", {}).get("blockReason") or "")
            reason_label = finish_reason or block_reason or "EMPTY_CANDIDATE_TEXT"
            logger.warning(
                "Gemini generateContent returned empty visible text: model=%s finishReason=%s thoughtsTokenCount=%d thoughtParts=%d latency_ms=%d",
                target_model,
                reason_label,
                thoughts_tokens,
                thought_parts_count,
                latency_ms,
            )
            raise IntegrationError(
                f"Gemini generateContent returned empty visible text (model={target_model}; finishReason={reason_label}; thoughtsTokens={thoughts_tokens})",
                details={
                    "status_code": 200,
                    "category": "EMPTY_MODEL_OUTPUT",
                    "google_status": reason_label,
                    "model": target_model,
                    "api_interface": "generate_content",
                    "safe_detail": f"Model returned HTTP 200 with 0 visible text chars (finishReason={reason_label}, thoughtsTokens={thoughts_tokens}).",
                },
            )

        return {
            "provider": "gemini",
            "api_interface": "generate_content",
            "model": target_model,
            "text": final_text,
            "finish_reason": finish_reason or "STOP",
            "function_calls": function_calls,
            "latency_ms": latency_ms,
            "usage": {
                "prompt_tokens": usage.get("promptTokenCount", 0),
                "completion_tokens": usage.get("candidatesTokenCount", 0),
                "thoughts_tokens": thoughts_tokens,
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
        target_model = model or self._settings.resolve_gemini_tier_model(2)
        endpoint = f"{self.base_url}/models/{target_model}:streamGenerateContent"
        effective_max_tokens = (
            max(max_output_tokens, 2048) if target_model.startswith("gemini-4") else max_output_tokens
        )
        gen_cfg: dict[str, Any] = {"maxOutputTokens": effective_max_tokens}
        if not _model_deprecates_sampling_params(target_model):
            gen_cfg["temperature"] = temperature
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": gen_cfg,
        }
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        def _consume_stream(client: httpx.Client) -> Generator[str, None, None]:
            with client.stream("POST", endpoint, headers=self._headers(), params={"alt": "sse"}, json=body, timeout=timeout_seconds) as resp:
                if resp.status_code >= 400:
                    g_status, g_msg = _extract_safe_google_error(resp)
                    extra = f" ({g_status}: {g_msg})" if (g_status or g_msg) else ""
                    raise IntegrationError(
                        f"Gemini stream failed: {classify_http_error(resp.status_code)}{extra}",
                        details={"status_code": resp.status_code, "model": target_model},
                    )
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
                            if part.get("thought") is True:
                                continue
                            if "text" in part and part["text"]:
                                yield part["text"]

        if self._client is not None:
            yield from _consume_stream(self._client)
        else:
            with httpx.Client(timeout=timeout_seconds) as client:
                yield from _consume_stream(client)

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
