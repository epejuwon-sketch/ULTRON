"""Multi-model LLM provider abstraction, 5-tier Gemini capability registry, controlled failover chain, and cost estimator for NEON."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import IntegrationError
from app.integrations.gemini import GeminiClient

# Published November 2026 USD per 1M tokens (input, output) for cost monitoring & budgeting
MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-4-hydrogen": (1.50, 7.50),
    "gemini-4-argon": (2.00, 10.00),
    "gemini-4-carbon": (2.00, 10.00),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-3-5-sonnet-latest": (3.00, 15.00),
    "llama3.2": (0.0, 0.0),
}

MODEL_CONTEXT_WINDOWS: dict[str, tuple[int, int]] = {
    "gemini-3.5-flash-lite": (1_048_576, 65_536),
    "gemini-3.8-flash": (1_048_576, 65_536),
    "gemini-4-hydrogen": (1_048_576, 65_536),
    "gemini-4-argon": (1_048_576, 65_536),
    "gemini-4-carbon": (1_048_576, 65_536),
    "gemini-2.5-flash": (1_048_576, 65_536),
    "gemini-2.5-flash-lite": (1_048_576, 65_536),
}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_rate, out_rate = MODEL_PRICING_PER_1M.get(model, (0.30, 2.50))
    cost = (prompt_tokens / 1_000_000.0) * in_rate + (completion_tokens / 1_000_000.0) * out_rate
    return round(cost, 6)


class BaseLLMProvider(ABC):
    provider_name: str

    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    def default_model(self) -> str:
        ...

    @abstractmethod
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
        timeout_seconds: float = 25.0,
    ) -> dict[str, Any]:
        ...


class GeminiLLMProvider(BaseLLMProvider):
    provider_name = "gemini"

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = GeminiClient(settings, http_client=http_client)

    def is_configured(self) -> bool:
        return self._client.is_configured()

    def default_model(self) -> str:
        return self._settings.resolve_gemini_tier_model(2)

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
        timeout_seconds: float = 25.0,
    ) -> dict[str, Any]:
        return self._client.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            model=model or self.default_model(),
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type=response_mime_type,
            response_schema=response_schema,
            function_declarations=function_declarations,
            multimodal_parts=multimodal_parts,
            timeout_seconds=timeout_seconds,
        )


class OpenAILLMProvider(BaseLLMProvider):
    provider_name = "openai"

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._http = http_client

    @property
    def _api_key(self) -> str:
        return self._settings.openai_api_key.get_secret_value().strip() if self._settings.openai_api_key else ""

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def default_model(self) -> str:
        return self._settings.openai_model_fallback

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
        timeout_seconds: float = 25.0,
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise IntegrationError("OPENAI_API_KEY is not configured.")
        target_model = model or self.default_model()
        endpoint = f"{self._settings.openai_base_url.rstrip('/')}/chat/completions"
        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        started = time.perf_counter()
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        body: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        if response_mime_type == "application/json":
            body["response_format"] = {"type": "json_object"}
        try:
            if self._http is not None:
                resp = self._http.post(endpoint, headers=headers, json=body, timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.post(endpoint, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise IntegrationError(f"OpenAI request failed: {type(exc).__name__}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if resp.status_code >= 400:
            raise IntegrationError(f"OpenAI HTTP {resp.status_code}")
        data = resp.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        return {
            "provider": "openai",
            "api_interface": "chat_completions",
            "model": target_model,
            "text": text,
            "latency_ms": latency_ms,
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }


class AnthropicLLMProvider(BaseLLMProvider):
    provider_name = "anthropic"

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._http = http_client

    @property
    def _api_key(self) -> str:
        return self._settings.anthropic_api_key.get_secret_value().strip() if self._settings.anthropic_api_key else ""

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def default_model(self) -> str:
        return self._settings.anthropic_model_fallback

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
        timeout_seconds: float = 25.0,
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise IntegrationError("ANTHROPIC_API_KEY is not configured.")
        target_model = model or self.default_model()
        endpoint = f"{self._settings.anthropic_base_url.rstrip('/')}/messages"
        started = time.perf_counter()
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": target_model,
            "max_tokens": max_output_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_instruction:
            body["system"] = system_instruction

        try:
            if self._http is not None:
                resp = self._http.post(endpoint, headers=headers, json=body, timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.post(endpoint, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Anthropic request failed: {type(exc).__name__}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if resp.status_code >= 400:
            raise IntegrationError(f"Anthropic HTTP {resp.status_code}")
        data = resp.json()
        blocks = data.get("content", [])
        text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        usage = data.get("usage", {})
        pt = usage.get("input_tokens", 0)
        ct = usage.get("output_tokens", 0)
        return {
            "provider": "anthropic",
            "api_interface": "messages",
            "model": target_model,
            "text": text,
            "latency_ms": latency_ms,
            "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
        }


class OllamaLLMProvider(BaseLLMProvider):
    provider_name = "ollama"

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._http = http_client

    def is_configured(self) -> bool:
        return bool(self._settings.ollama_base_url.strip())

    def default_model(self) -> str:
        return self._settings.ollama_model_local

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
        timeout_seconds: float = 25.0,
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise IntegrationError("OLLAMA_BASE_URL is not configured.")
        target_model = model or self.default_model()
        endpoint = f"{self._settings.ollama_base_url.rstrip('/')}/api/generate"
        started = time.perf_counter()
        body: dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_output_tokens},
        }
        if system_instruction:
            body["system"] = system_instruction
        try:
            if self._http is not None:
                resp = self._http.post(endpoint, json=body, timeout=timeout_seconds)
            else:
                with httpx.Client(timeout=timeout_seconds) as client:
                    resp = client.post(endpoint, json=body)
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Ollama request failed: {type(exc).__name__}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if resp.status_code >= 400:
            raise IntegrationError(f"Ollama HTTP {resp.status_code}")
        data = resp.json()
        pt = int(data.get("prompt_eval_count", 0))
        ct = int(data.get("eval_count", 0))
        return {
            "provider": "ollama",
            "api_interface": "ollama_generate",
            "model": target_model,
            "text": data.get("response", "").strip(),
            "latency_ms": latency_ms,
            "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
        }


def build_gemini_tier_fallback_chain(
    primary_model: str,
    settings: Settings,
    *,
    reasoning_tier: int | None = None,
) -> list[str]:
    """Construct a controlled, deduplicated intra-Gemini fallback chain per reasoning tier.

    Ensures paid-only Gemini 4 models (e.g., gemini-4-carbon / gemini-4-argon) gracefully
    cascade to free+paid Gemini 4 Hydrogen and Gemini 3.8/3.5/2.5 Flash models while
    honestly flagging `fallback_used=True` whenever the actual model differs from primary.
    """
    if reasoning_tier is None:
        if (primary_model or "").strip().startswith("gemini-4"):
            t = 5
        elif "flash-lite" in (primary_model or "").strip():
            t = 1
        else:
            t = 2
    else:
        t = max(1, min(5, int(reasoning_tier)))
    if t == 1:
        ordered = [
            primary_model,
            settings.resolve_gemini_tier_model(1),
            "gemini-2.5-flash-lite",
            settings.resolve_gemini_tier_model(2),
            "gemini-2.5-flash",
        ]
    elif t == 2:
        ordered = [
            primary_model,
            settings.resolve_gemini_tier_model(2),
            settings.resolve_gemini_tier_model(1),
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ]
    elif t == 3:
        ordered = [
            primary_model,
            settings.resolve_gemini_tier_model(3),
            "gemini-4-hydrogen",
            settings.resolve_gemini_tier_model(1),
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ]
    elif t == 4:
        ordered = [
            primary_model,
            "gemini-4-hydrogen",
            settings.resolve_gemini_tier_model(3),
            settings.resolve_gemini_tier_model(1),
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ]
    else:
        ordered = [
            primary_model,
            *(["gemini-4-argon"] if primary_model != "gemini-4-argon" else []),
            "gemini-4-hydrogen",
            settings.resolve_gemini_tier_model(3),
            settings.resolve_gemini_tier_model(1),
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ]

    seen: set[str] = set()
    result: list[str] = []
    for m in ordered:
        clean = (m or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


# Backwards-compatible alias for any internal callers/tests
def _build_gemini_model_candidates(primary_model: str, settings: Settings, reasoning_tier: int | None = None) -> list[str]:
    return build_gemini_tier_fallback_chain(primary_model, settings, reasoning_tier=reasoning_tier)


def get_model_capability_registry(settings: Settings) -> list[dict[str, Any]]:
    """Honest model capability registry across all 5 configured Gemini tiers + optional failover providers."""
    gemini_ok = bool(settings.gemini_api_key and settings.gemini_api_key.get_secret_value().strip())
    openai_ok = bool(settings.openai_api_key and settings.openai_api_key.get_secret_value().strip())
    anthropic_ok = bool(settings.anthropic_api_key and settings.anthropic_api_key.get_secret_value().strip())
    ollama_ok = bool(settings.ollama_base_url.strip())

    # Group configured tiers by model ID while preserving tier order
    gemini_model_tiers: dict[str, list[int]] = {}
    for tier_num in range(1, 6):
        mid = settings.resolve_gemini_tier_model(tier_num)
        gemini_model_tiers.setdefault(mid, []).append(tier_num)

    entries: list[dict[str, Any]] = []
    for mid, tier_list in gemini_model_tiers.items():
        ctx_in, ctx_out = MODEL_CONTEXT_WINDOWS.get(mid, (1_048_576, 65_536))
        entries.append(
            {
                "provider": "gemini",
                "role": "primary",
                "model": mid,
                "tiers": tier_list,
                "api_interface": settings.gemini_api_mode,
                "input_token_limit": ctx_in,
                "output_token_limit": ctx_out,
                "supports_streaming": True,
                "supports_structured_output": True,
                "supports_tool_calling": True,
                "supports_interactions_api": True,
                "configured": gemini_ok,
                "capability_state": "INSTALLED" if gemini_ok else "DEFINED_NOT_INSTALLED",
                "pricing_per_1m_usd": MODEL_PRICING_PER_1M.get(mid, (0.30, 2.50)),
            }
        )

    entries.extend(
        [
            {
                "provider": "openai",
                "role": "secondary_failover",
                "model": settings.openai_model_fallback,
                "tiers": [2, 3],
                "api_interface": "chat_completions",
                "supports_streaming": True,
                "supports_structured_output": True,
                "supports_tool_calling": True,
                "configured": openai_ok,
                "capability_state": "INSTALLED" if openai_ok else "DEFINED_NOT_INSTALLED",
                "pricing_per_1m_usd": MODEL_PRICING_PER_1M.get(settings.openai_model_fallback, (0.15, 0.60)),
            },
            {
                "provider": "anthropic",
                "role": "secondary_failover",
                "model": settings.anthropic_model_fallback,
                "tiers": [3, 4, 5],
                "api_interface": "messages",
                "supports_streaming": True,
                "supports_structured_output": True,
                "supports_tool_calling": True,
                "configured": anthropic_ok,
                "capability_state": "INSTALLED" if anthropic_ok else "DEFINED_NOT_INSTALLED",
                "pricing_per_1m_usd": MODEL_PRICING_PER_1M.get(settings.anthropic_model_fallback, (3.00, 15.00)),
            },
            {
                "provider": "ollama",
                "role": "local_failover",
                "model": settings.ollama_model_local,
                "tiers": [1, 2],
                "api_interface": "ollama_generate",
                "supports_streaming": True,
                "supports_structured_output": True,
                "supports_tool_calling": False,
                "configured": ollama_ok,
                "capability_state": "INSTALLED" if ollama_ok else "DEFINED_NOT_INSTALLED",
                "pricing_per_1m_usd": (0.0, 0.0),
            },
        ]
    )
    return entries


def execute_with_failover(
    *,
    settings: Settings,
    prompt: str,
    system_instruction: str | None,
    primary_model: str,
    reasoning_tier: int | None = None,
    temperature: float = 0.2,
    max_output_tokens: int = 1024,
    response_mime_type: str | None = None,
    response_schema: dict[str, Any] | None = None,
    function_declarations: list[dict[str, Any]] | None = None,
    multimodal_parts: list[dict[str, Any]] | None = None,
    max_retries_per_provider: int = 1,
    timeout_seconds: float | None = None,
    providers: list[BaseLLMProvider] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Execute prompt across configured providers in priority order with controlled per-tier Gemini fallback."""
    effective_timeout = timeout_seconds if timeout_seconds is not None else settings.gemini_request_timeout_seconds
    chain = providers or [
        GeminiLLMProvider(settings),
        OpenAILLMProvider(settings),
        AnthropicLLMProvider(settings),
        OllamaLLMProvider(settings),
    ]
    configured_chain = [p for p in chain if p.is_configured()]
    errors: list[dict[str, str]] = []

    for provider in configured_chain:
        if provider.provider_name == "gemini" and max_retries_per_provider >= 1:
            candidate_models = build_gemini_tier_fallback_chain(
                primary_model,
                settings,
                reasoning_tier=reasoning_tier,
            )
            for idx, target_model in enumerate(candidate_models):
                try:
                    result = provider.generate(
                        prompt=prompt,
                        system_instruction=system_instruction,
                        model=target_model,
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                        response_mime_type=response_mime_type,
                        response_schema=response_schema,
                        function_declarations=function_declarations,
                        multimodal_parts=multimodal_parts,
                        timeout_seconds=effective_timeout,
                    )
                    return result, errors
                except Exception as exc:
                    details = getattr(exc, "details", {}) if isinstance(exc, IntegrationError) else {}
                    status_code = details.get("status_code") if isinstance(details, dict) else None
                    google_status = str(details.get("google_status") or "") if isinstance(details, dict) else ""
                    err_entry: dict[str, str] = {
                        "provider": provider.provider_name,
                        "model": target_model,
                        "attempt": str(idx + 1),
                        "error": str(exc),
                    }
                    if status_code is not None:
                        err_entry["http_status"] = str(status_code)
                    if google_status:
                        err_entry["google_status"] = google_status
                    errors.append(err_entry)
                    # Stop trying other Gemini models immediately if the API key itself is invalid (401/API_KEY_INVALID)
                    if status_code == 401 or "API_KEY_INVALID" in str(exc):
                        break
                    if idx + 1 < len(candidate_models):
                        time.sleep(0.1)
            continue

        target_model = primary_model if provider.provider_name == "gemini" else provider.default_model()
        for attempt in range(max_retries_per_provider + 1):
            try:
                gen_kwargs: dict[str, Any] = {
                    "prompt": prompt,
                    "system_instruction": system_instruction,
                    "model": target_model,
                    "temperature": temperature,
                    "max_output_tokens": max_output_tokens,
                    "response_mime_type": response_mime_type,
                    "response_schema": response_schema,
                    "function_declarations": function_declarations,
                    "timeout_seconds": effective_timeout,
                }
                if provider.provider_name == "gemini" and multimodal_parts:
                    gen_kwargs["multimodal_parts"] = multimodal_parts
                result = provider.generate(**gen_kwargs)
                return result, errors
            except Exception as exc:
                errors.append(
                    {
                        "provider": provider.provider_name,
                        "model": target_model,
                        "attempt": str(attempt + 1),
                        "error": str(exc),
                    }
                )
                if attempt < max_retries_per_provider:
                    time.sleep(min(0.25 * (attempt + 1), 1.0))

    return None, errors
