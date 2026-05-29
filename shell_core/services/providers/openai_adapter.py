"""openai_adapter.py — the OpenAI `ProviderAdapter` (agnostic-runtime §3.4).

The second adapter, and the first that does real message restructuring.
OpenAI's Chat Completions wire format differs structurally from the
normalized (Anthropic-shaped) contract in `base.py`:

  - `system` is a message, not a separate field;
  - an assistant turn carries its tool calls in a `tool_calls` array, not as
    content blocks;
  - each tool result is its own `role:"tool"` message.

`format_request` and `parse_response` translate across that gap — the
dispatcher loop never sees it. This adapter is the proof that the normalized
contract is genuinely provider-neutral and not just Anthropic in disguise.

`cost()` returns 0.0 — the dispatcher is tokens-only in alpha (decision #108).
"""

from __future__ import annotations

import json
import os

import openai

from .base import ParsedResponse, ProviderAdapter, ProviderError

# OpenAI finish_reason -> normalized stop_reason (see base.py vocabulary).
_STOP_REASON = {
    "tool_calls": "tool_use",
    "stop": "end_turn",
    "length": "max_tokens",
}


class OpenAIAdapter(ProviderAdapter):
    """OpenAI Chat Completions behind the normalized seam."""

    provider = "openai"

    def __init__(self, endpoint: str | None = None) -> None:
        # max_retries=5 — the SDK retries 429/5xx internally; ProviderError is
        # raised only once that budget is spent. `endpoint` is accepted for
        # interface uniformity (see get_adapter) and ignored here.
        #
        # When BROKER_BASE is set (Phase 1), route through the credential broker
        # (the broker injects Authorization on egress; the placeholder api_key
        # is overwritten). base_url carries the `/v1` suffix the SDK expects, so
        # it requests {broker}/openai/v1/chat/completions. NOTE: this is the
        # `openai` provider only — OllamaAdapter subclasses ProviderAdapter (not
        # this class) and is unaffected.
        broker = os.environ.get("BROKER_BASE")
        if broker:
            self._client = openai.OpenAI(
                base_url=f"{broker.rstrip('/')}/openai/v1",
                api_key="broker-injected", max_retries=5)
        else:
            self._client = openai.OpenAI(max_retries=5)

    @staticmethod
    def _to_native_messages(messages: list) -> list:
        """Normalized messages -> OpenAI Chat Completions messages.

        A normalized assistant turn (text + tool_use blocks) collapses into
        one assistant message with a `tool_calls` array; a normalized
        tool-result turn fans out into one `role:"tool"` message per result.
        String content (plain user/assistant text, e.g. from history) passes
        straight through.
        """
        out: list[dict] = []
        for m in messages:
            role, content = m["role"], m["content"]
            if isinstance(content, str):
                out.append({"role": role, "content": content})
                continue
            if role == "assistant":
                text = "\n".join(b["text"] for b in content if b["type"] == "text")
                tool_calls = [
                    {
                        "id": b["id"],
                        "type": "function",
                        "function": {
                            "name": b["name"],
                            "arguments": json.dumps(b["input"]),
                        },
                    }
                    for b in content
                    if b["type"] == "tool_use"
                ]
                msg = {"role": "assistant", "content": text or None}
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                out.append(msg)
            else:
                # A user-role turn carrying tool_result blocks — each becomes
                # its own role:"tool" message keyed by the tool-call id.
                for b in content:
                    if b["type"] == "tool_result":
                        out.append({
                            "role": "tool",
                            "tool_call_id": b["tool_use_id"],
                            "content": b["content"],
                        })
        return out

    def format_request(
        self,
        system_blocks: list,
        tools: list,
        messages: list,
        model: str,
        max_tokens: int,
    ) -> dict:
        native_messages: list[dict] = []
        # system: the normalized {text, cache} blocks join into one system
        # message. OpenAI prefix-caches automatically — `cache` needs no marker.
        system_text = "\n\n".join(b["text"] for b in system_blocks)
        if system_text:
            native_messages.append({"role": "system", "content": system_text})
        native_messages.extend(self._to_native_messages(messages))

        request = {
            "model": model,
            "max_completion_tokens": max_tokens,
            "messages": native_messages,
        }
        if tools:
            request["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["spec"],
                    },
                }
                for t in tools
            ]
        return request

    def call(self, request: dict):
        try:
            return self._client.chat.completions.create(**request)
        except openai.APIError as e:
            # SDK retries (max_retries=5) already exhausted — normalize so the
            # dispatcher never catches a provider-native exception.
            raise ProviderError(f"{type(e).__name__}: {e}") from e

    def parse_response(self, response) -> ParsedResponse:
        choice = response.choices[0]
        message = choice.message
        text = (message.content or "").strip()

        tool_calls = []
        for tc in message.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                {"id": tc.id, "name": tc.function.name, "input": args}
            )

        u = response.usage
        prompt_tokens = u.prompt_tokens if u else 0
        # OpenAI reports the cached prefix under prompt_tokens_details; the
        # remainder of the prompt is processed fresh. Older or non-compliant
        # responses omit the detail object — default to a zero hit.
        cache_hit = 0
        details = getattr(u, "prompt_tokens_details", None) if u else None
        if details is not None:
            cache_hit = getattr(details, "cached_tokens", 0) or 0
        return ParsedResponse(
            text=text,
            tool_calls=tool_calls,
            usage={
                "input_tokens":      prompt_tokens,
                "output_tokens":     u.completion_tokens if u else 0,
                "cache_hit_tokens":  cache_hit,
                "cache_miss_tokens": max(prompt_tokens - cache_hit, 0),
            },
            stop_reason=_STOP_REASON.get(choice.finish_reason, "other"),
        )

    def cost(self, usage: dict, model: str) -> float:
        # Per-model rates live in the `models` registry; tokens-only in alpha
        # (decision #108). Completes the seam interface; not called yet.
        return 0.0
