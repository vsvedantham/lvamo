"""The model behind one small interface (principle 7). Today: a llama.cpp server
(OpenAI-compatible) on our VM or a separate model host; a hosted API can
implement the same `complete_json` later."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

from app.config import settings


class ModelError(RuntimeError):
    """The model call failed or returned something unusable."""


class AnswerCutOff(ModelError):
    """The answer hit max_tokens. The same prompt would be cut off again, so it isn't retried."""


@dataclass
class Completion:
    data: dict
    model: str
    prompt_tokens: int | None
    output_tokens: int | None
    duration_ms: int


class Provider(Protocol):
    name: str

    async def complete_json(self, system: str, user: str, schema: dict, max_tokens: int) -> Completion: ...


class LlamaServerProvider:
    """llama-server's /v1/chat/completions with a JSON-schema-constrained answer.
    The system prompt goes first and stays identical across a user's jobs, so
    the server reuses its cached prefix and only reads each job's own tokens."""

    def __init__(self, base_url: str, api_key: str = "", model: str = "local", timeout: int = 900):
        from openai import AsyncOpenAI
        self.name = model
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key or "none", timeout=timeout, max_retries=0)

    async def complete_json(self, system: str, user: str, schema: dict, max_tokens: int) -> Completion:
        started = time.monotonic()
        try:
            resp = await self._client.chat.completions.create(
                model=self.name,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.2,
                max_tokens=max_tokens,
                response_format={"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}},
                extra_body={"chat_template_kwargs": {"enable_thinking": False}, "cache_prompt": True},
            )
        except Exception as exc:  # noqa: BLE001  (network, timeout, server error: all retryable)
            raise ModelError(f"model call failed: {type(exc).__name__}: {exc}") from exc
        text = resp.choices[0].message.content or ""
        if resp.choices[0].finish_reason == "length":
            raise AnswerCutOff(f"answer cut off at {max_tokens} tokens: {text[:200]!r}")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ModelError(f"model returned invalid JSON: {text[:200]!r}") from exc
        usage = resp.usage
        return Completion(data=data, model=self.name,
                          prompt_tokens=usage.prompt_tokens if usage else None,
                          output_tokens=usage.completion_tokens if usage else None,
                          duration_ms=int((time.monotonic() - started) * 1000))


_provider: Provider | None = None


def get_provider() -> Provider:
    """The configured model. Raises ModelError when none is configured."""
    global _provider
    if _provider is None:
        if not settings.applaut_llm_base_url:
            raise ModelError("APPLAUT_LLM_BASE_URL is not set")
        _provider = LlamaServerProvider(settings.applaut_llm_base_url, settings.applaut_llm_api_key,
                                        settings.applaut_llm_model, settings.applaut_llm_timeout_seconds)
    return _provider


def set_provider(provider: Provider | None) -> None:
    """Tests swap in a fake model."""
    global _provider
    _provider = provider
