"""ollama_adapter.py — the Ollama `ProviderAdapter` (agnostic-runtime §3.4).

Ollama exposes an OpenAI-compatible Chat Completions endpoint at `/v1`, so
this adapter inherits `OpenAIAdapter` and swaps two things:

  - the SDK client's `base_url` points at the Ollama server (per-model, from
    `models.endpoint`);
  - the request uses `max_tokens` instead of the newer `max_completion_tokens`
    — Ollama's compat layer carries the older parameter name.

The full translation (system-as-message, `tool_calls` array, `role:"tool"`
fan-out, `finish_reason` normalization, JSON-arg round-trip) is inherited
unchanged. `tool_dialect='openai'` works for tool-capable local models
(qwen2.5, llama3.x with tools, qwen3, …) — they call tools natively.

The `parsed` dialect — for local models *without* native function calling,
the §5.3 / §11 make-or-break spike — is a separate concern: a different
adapter shape that prompts the protocol and parses it from text. Not here.

`cost()` returns 0.0 — local models have no per-token dollar cost.
"""

from __future__ import annotations

import os

import openai

from .openai_adapter import OpenAIAdapter


class OllamaAdapter(OpenAIAdapter):
    """Ollama's OpenAI-compatible endpoint, behind the normalized seam."""

    provider = "local"

    def __init__(self, endpoint: str | None = None) -> None:
        # base_url precedence: explicit arg -> OLLAMA_API_BASE env -> default.
        # The SDK requires an api_key string; Ollama ignores it.
        base_url = (
            endpoint
            or os.environ.get("OLLAMA_API_BASE")
            or "http://localhost:11434/v1"
        )
        self._client = openai.OpenAI(base_url=base_url, api_key="ollama")
        self._base_url = base_url

    def format_request(
        self,
        system_blocks: list,
        tools: list,
        messages: list,
        model: str,
        max_tokens: int,
    ) -> dict:
        # Reuse OpenAIAdapter's full translation, then rename the token param
        # for Ollama's compat layer.
        request = super().format_request(system_blocks, tools, messages, model, max_tokens)
        if "max_completion_tokens" in request:
            request["max_tokens"] = request.pop("max_completion_tokens")
        return request
