"""anthropic_adapter.py — the Anthropic `ProviderAdapter` (agnostic-runtime §3.4).

The first and reference adapter. It owns the only `import anthropic` in the
runtime; the dispatcher speaks the normalized contract in `base.py`.

A0 is a pure refactor — this adapter reproduces the dispatcher's prior
Anthropic behavior byte-for-byte:
  - the SDK client is created with `max_retries=5`;
  - `messages` stays in Anthropic wire shape between turns, so `format_request`
    is an identity over it (real translation arrives with A1's OpenAI adapter);
  - `cost()` returns 0.0 — the dispatcher is tokens-only in alpha (decision
    #108) and per-model rates land with the `models` registry (CC-50).
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
        # `system_blocks`, `tools`, and `messages` are already Anthropic-shaped
        # (A0). The request is the kwargs dict for `messages.create`.
        return {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "tools": tools,
            "messages": messages,
        }

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
        # Per-model rates live in the `models` registry (CC-50); until then the
        # dispatcher is tokens-only (decision #108). The method completes the
        # seam interface; the dispatcher does not call it in alpha.
        return 0.0

    def serialize_assistant(self, response) -> dict:
        content = []
        for b in response.content:
            if b.type == "text":
                content.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                content.append(
                    {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                )
        return {"role": "assistant", "content": content}

    def serialize_tool_results(self, results: list[dict]) -> dict:
        content = []
        for r in results:
            block = {
                "type": "tool_result",
                "tool_use_id": r["id"],
                "content": r["content"],
            }
            if r.get("is_error"):
                block["is_error"] = True
            content.append(block)
        return {"role": "user", "content": content}
