"""anthropic_adapter.py — the Anthropic `ProviderAdapter` (agnostic-runtime §3.4).

The first and reference adapter. It owns the only `import anthropic` in the
runtime; the dispatcher speaks the normalized contract in `base.py`.

Anthropic's content-block model *is* the normalized message format (base.py
picks it as the reference dialect), so `format_request` does no message
restructuring — it only adds a cache breakpoint to the last message, and
projects `system` (cache hints) and `tools` (the tool-call dialect). The
OpenAI / Gemini / local adapters do real message restructuring here.

`cost()` returns 0.0 — the dispatcher is tokens-only in alpha (decision
#108); per-model rates land with the `models` registry consumers (CC-52/53).
"""

from __future__ import annotations

import anthropic

from .base import ParsedResponse, ProviderAdapter, ProviderError


def _breakpoint_messages(messages: list) -> list:
    """Copy `messages`, placing a cache breakpoint on the last message's final
    content block. The system breakpoint caches the boot document; this one
    caches the conversation prefix, so each iteration of the dispatcher's tool
    loop reads the previous iteration's transcript from cache instead of
    re-prefilling it. Copied, never mutated — the dispatcher reuses the same
    `messages` list across loop iterations, so an in-place edit would leave
    stale breakpoints on old messages and overrun Anthropic's four-slot cap."""
    if not messages:
        return messages
    out = list(messages)
    last = dict(out[-1])
    content = last["content"]
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    else:
        content = [dict(b) for b in content]
    if content:
        content[-1] = {**content[-1], "cache_control": {"type": "ephemeral"}}
    last["content"] = content
    out[-1] = last
    return out


class AnthropicAdapter(ProviderAdapter):
    """Anthropic Messages API behind the normalized seam."""

    provider = "anthropic"

    def __init__(self, endpoint: str | None = None) -> None:
        # max_retries=5 — the SDK retries 429/5xx/overloaded internally;
        # ProviderError is raised only once that budget is spent. `endpoint`
        # is accepted for interface uniformity (see get_adapter) and ignored;
        # this adapter uses the Anthropic SDK default base URL.
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
            # shape — passed through unchanged but for a cache breakpoint on
            # the last message, so the conversation prefix caches turn to turn.
            "messages": _breakpoint_messages(messages),
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
        # Cache fields: cache_read is the prefix served from cache (a hit);
        # input + cache_creation is processed fresh (a miss — cache writes
        # included). getattr — responses predating prompt caching omit them.
        cache_read     = getattr(u, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(u, "cache_creation_input_tokens", 0) or 0
        return ParsedResponse(
            text=text,
            tool_calls=tool_calls,
            usage={
                "input_tokens":      u.input_tokens,
                "output_tokens":     u.output_tokens,
                "cache_hit_tokens":  cache_read,
                "cache_miss_tokens": u.input_tokens + cache_creation,
            },
            stop_reason=response.stop_reason,
        )

    def cost(self, usage: dict, model: str) -> float:
        # Per-model rates live in the `models` registry; until their consumers
        # land the dispatcher is tokens-only (decision #108). The method
        # completes the seam interface; the dispatcher does not call it.
        return 0.0
