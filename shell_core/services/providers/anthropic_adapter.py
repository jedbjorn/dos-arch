"""anthropic_adapter.py — the Anthropic `ProviderAdapter` (agnostic-runtime §3.4).

The first and reference adapter. It owns the only `import anthropic` in the
runtime; the dispatcher speaks the normalized contract in `base.py`.

Anthropic's content-block model *is* the normalized message format (base.py
picks it as the reference dialect), so `format_request`'s message
translation is an identity — only `system` (cache hints) and `tools` (the
tool-call dialect) need projection. The OpenAI / Gemini / local adapters do
real message restructuring here.

`cost()` returns 0.0 — the dispatcher is tokens-only in alpha (decision
#108); per-model rates land with the `models` registry consumers (CC-52/53).
"""

from __future__ import annotations

import anthropic

from .base import ParsedResponse, ProviderAdapter, ProviderError


class AnthropicAdapter(ProviderAdapter):
    """Anthropic Messages API behind the normalized seam."""

    provider = "anthropic"

    def __init__(self) -> None:
        # max_retries=5 — the SDK retries 429/5xx/overloaded internally;
        # ProviderError is raised only once that budget is spent.
        self._client = anthropic.Anthropic(max_retries=5)

    def format_request(
        self,
        system_blocks: list,
        tools: list,
        messages: list,
        model: str,
        max_tokens: int,
    ) -> dict:
        # system: normalized {text, cache} -> Anthropic text blocks, with
        # cache_control on the spans flagged cacheable.
        system = []
        for b in system_blocks:
            block = {"type": "text", "text": b["text"]}
            if b.get("cache"):
                block["cache_control"] = {"type": "ephemeral"}
            system.append(block)

        # tools: normalized {name, description, spec} -> Anthropic tool shape.
        native_tools = [
            {"name": t["name"], "description": t["description"], "input_schema": t["spec"]}
            for t in tools
        ]

        request = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            # messages: the normalized format is Anthropic's content-block
            # shape, so this reference adapter passes them through unchanged.
            "messages": messages,
        }
        if native_tools:
            request["tools"] = native_tools
        return request

    def call(self, request: dict):
        try:
            return self._client.messages.create(**request)
        except anthropic.APIError as e:
            # SDK retries (max_retries=5) already exhausted — normalize so the
            # dispatcher never catches a provider-native exception.
            raise ProviderError(f"{type(e).__name__}: {e}") from e

    def parse_response(self, response) -> ParsedResponse:
        text = "\n".join(
            b.text for b in response.content if b.type == "text"
        ).strip()
        tool_calls = [
            {"id": b.id, "name": b.name, "input": b.input}
            for b in response.content
            if b.type == "tool_use"
        ]
        u = response.usage
        return ParsedResponse(
            text=text,
            tool_calls=tool_calls,
            usage={"input_tokens": u.input_tokens, "output_tokens": u.output_tokens},
            stop_reason=response.stop_reason,
        )

    def cost(self, usage: dict, model: str) -> float:
        # Per-model rates live in the `models` registry; until their consumers
        # land the dispatcher is tokens-only (decision #108). The method
        # completes the seam interface; the dispatcher does not call it.
        return 0.0
