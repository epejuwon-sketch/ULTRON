"""Multi-model LLM provider abstraction, capability registry, failover chain, and cost estimator for NEON."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import IntegrationError
from app.integrations.gemini import GeminiClient

# Estimated USD per 1M tokens (input, output) for cost monitoring & budgeting
MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-3-5-sonnet-latest": (3.00, 15.00),
    "llama3.2": (0.0, 0.0),
}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_rate, out_rate = MODEL_PRICING_PER_1M.get(model, (0.20, 0.80))
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
        timeout_seconds: float = 20.0,
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
        return self._settings.gemini_model_standard

    def generate(
        self,
        *,
        prompt: str,
        system_instruction: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        timeout_seconds: float = 20.0,
    ) -> dict[str, Any]:
        return self._client.generate_content(
            prompt=prompt,
            system_instruction=system_instruction,
            model=model or self.default_model(),
            temperature=temperature,
            max_output_tokens=max_output_tokens,
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
        timeout_seconds: float = 20.0,
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
        body = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
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
        timeout_seconds: float = 20.0,
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
        timeout_seconds: float = 20.0,
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
            "model": target_model,
            "text": data.get("response", "").strip(),
            "latency_ms": latency_ms,
            "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
        }


def get_model_capability_registry(settings: Settings) -> list[dict[str, Any]]:
    """Honest model capability registry across all supported NEON providers."""
    gemini_ok = bool(settings.gemini_api_key and settings.gemini_api_key.get_secret_value().strip())
    openai_ok = bool(settings.openai_api_key and settings.openai_api_key.get_secret_value().strip())
    anthropic_ok = bool(settings.anthropic_api_key and settings.anthropic_api_key.get_secret_value().strip())
    ollama_ok = bool(settings.ollama_base_url.strip())

    return [
        {
            "provider": "gemini",
            "model": settings.gemini_model_fast,
            "tiers": [1],
            "supports_streaming": True,
            "supports_structured_output": True,
            "supports_tool_calling": True,
            "configured": gemini_ok,
            "capability_state": "INSTALLED" if gemini_ok else "DEFINED_NOT_INSTALLED",
            "pricing_per_1m_usd": MODEL_PRICING_PER_1M.get(settings.gemini_model_fast, (0.075, 0.30)),
        },
        {
            "provider": "gemini",
            "model": settings.gemini_model_standard,
            "tiers": [2, 3],
            "supports_streaming": True,
            "supports_structured_output": True,
            "supports_tool_calling": True,
            "configured": gemini_ok,
            "capability_state": "INSTALLED" if gemini_ok else "DEFINED_NOT_INSTALLED",
            "pricing_per_1m_usd": MODEL_PRICING_PER_1M.get(settings.gemini_model_standard, (0.10, 0.40)),
        },
        {
            "provider": "gemini",
            "model": settings.gemini_model_reasoning,
            "tiers": [4, 5],
            "supports_streaming": True,
            "supports_structured_output": True,
            "supports_tool_calling": True,
            "configured": gemini_ok,
            "capability_state": "INSTALLED" if gemini_ok else "DEFINED_NOT_INSTALLED",
            "pricing_per_1m_usd": MODEL_PRICING_PER_1M.get(settings.gemini_model_reasoning, (1.25, 10.00)),
        },
        {
            "provider": "openai",
            "model": settings.openai_model_fallback,
            "tiers": [2, 3],
            "supports_streaming": True,
            "supports_structured_output": True,
            "supports_tool_calling": True,
            "configured": openai_ok,
            "capability_state": "INSTALLED" if openai_ok else "DEFINED_NOT_INSTALLED",
            "pricing_per_1m_usd": MODEL_PRICING_PER_1M.get(settings.openai_model_fallback, (0.15, 0.60)),
        },
        {
            "provider": "anthropic",
            "model": settings.anthropic_model_fallback,
            "tiers": [3, 4, 5],
            "supports_streaming": True,
            "supports_structured_output": True,
            "supports_tool_calling": True,
            "configured": anthropic_ok,
            "capability_state": "INSTALLED" if anthropic_ok else "DEFINED_NOT_INSTALLED",
            "pricing_per_1m_usd": MODEL_PRICING_PER_1M.get(settings.anthropic_model_fallback, (3.00, 15.00)),
        },
        {
            "provider": "ollama",
            "model": settings.ollama_model_local,
            "tiers": [1, 2],
            "supports_streaming": True,
            "supports_structured_output": True,
            "supports_tool_calling": False,
            "configured": ollama_ok,
            "capability_state": "INSTALLED" if ollama_ok else "DEFINED_NOT_INSTALLED",
            "pricing_per_1m_usd": (0.0, 0.0),
        },
    ]


def execute_with_failover(
    *,
    settings: Settings,
    prompt: str,
    system_instruction: str | None,
    primary_model: str,
    temperature: float = 0.2,
    max_output_tokens: int = 1024,
    max_retries_per_provider: int = 1,
    timeout_seconds: float = 20.0,
    providers: list[BaseLLMProvider] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Execute prompt across configured providers in priority order with retry & failover."""
    chain = providers or [
        GeminiLLMProvider(settings),
        OpenAILLMProvider(settings),
        AnthropicLLMProvider(settings),
        OllamaLLMProvider(settings),
    ]
    configured_chain = [p for p in chain if p.is_configured()]
    errors: list[dict[str, str]] = []

    for provider in configured_chain:
        target_model = primary_model if provider.provider_name == "gemini" else provider.default_model()
        for attempt in range(max_retries_per_provider + 1):
            try:
                result = provider.generate(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    model=target_model,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    timeout_seconds=timeout_seconds,
                )
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
