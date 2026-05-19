"""base.py — the `ProviderAdapter` seam (agnostic-runtime §3.4).

The dispatcher thinks in one normalized vocabulary; each adapter projects
that vocabulary onto its provider's wire format. Every provider-specific
import, type, and exception lives behind this interface — the dispatcher
loop never names a provider.

The normalized contract — `format_request` projects it onto a native
request, `parse_response` lifts a native response back into it:

    format_request(system_blocks, tools, messages, model, max_tokens)
        -> native request          (whatever `call` consumes)
    call(request)
        -> native response         (whatever `parse_response` consumes)
    parse_response(response)
        -> ParsedResponse           (text, tool_calls, usage, stop_reason)
    cost(usage, model)
        -> float (USD)

That is the whole interface. Building the *next* turn's messages from a
`ParsedResponse` is provider-blind — `assistant_message` and
`tool_result_message` below do it generically — so it is not the adapter's
job.

── The normalized format ──────────────────────────────────────────────────

System block — one cacheable-or-not span of system text:
    {"text": str, "cache": bool}

Message — `messages` is a list of these:
    {"role": "user" | "assistant", "content": str | [block, ...]}
A plain string is shorthand for a single text block.

Content block — one of:
    {"type": "text",        "text": str}
    {"type": "tool_use",    "id": str, "name": str, "input": dict}
    {"type": "tool_result", "tool_use_id": str, "content": str,
                            "is_error": bool}   # is_error omitted when false

Tool — `tools` is a list of these (`spec` is a JSON-Schema object):
    {"name": str, "description": str, "spec": dict}

The block shape is Anthropic's content-block model — a deliberate choice of
reference dialect, expressive enough to carry every provider. The Anthropic
adapter's message translation is therefore an identity; non-reference
adapters (OpenAI, Gemini, local) do real restructuring in `format_request`
and `parse_response`.

Normalized `stop_reason` vocabulary — every adapter maps its provider's
terminal reasons onto this set:

    tool_use   — the model wants tool results; the loop continues
    end_turn   — the model is done; capture the final text
    max_tokens — output cap hit
    other      — any remaining provider-specific reason
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedResponse:
    """The provider-blind view of one model response.

    text        — the assistant's text, joined across text blocks.
    tool_calls  — [{"id": str, "name": str, "input": dict}], empty if none.
    usage       — {"input_tokens": int, "output_tokens": int}.
    stop_reason — normalized; see the vocabulary in the module docstring.
    """

    text: str
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    stop_reason: str = "other"


class ProviderError(Exception):
    """A model-call failure surfaced to the dispatcher.

    Raised by `call()` once the adapter's own retries are exhausted. The
    dispatcher catches this and never a provider-native exception type — that
    is the property keeping the loop provider-blind.
    """


class ProviderAdapter(ABC):
    """One provider speaking the runtime's normalized contract."""

    #: provider key — matches `models.provider` (`anthropic` / `openai` / ...).
    provider: str = ""

    @abstractmethod
    def format_request(
        self,
        system_blocks: list,
        tools: list,
        messages: list,
        model: str,
        max_tokens: int,
    ):
        """Project the normalized call onto the provider's native request."""

    @abstractmethod
    def call(self, request):
        """Send a native request, return the native response.

        Raises `ProviderError` once provider-level retries are exhausted.
        """

    @abstractmethod
    def parse_response(self, response) -> ParsedResponse:
        """Normalize a native response into a `ParsedResponse`."""

    @abstractmethod
    def cost(self, usage: dict, model: str) -> float:
        """USD cost for one call's `usage` on `model`. 0.0 for local models."""


# ── Normalized message construction (provider-blind) ──────────────────────────

def assistant_message(parsed: ParsedResponse) -> dict:
    """The assistant turn — text then tool_use blocks — as a `messages` entry.

    Built from the normalized `ParsedResponse`, so it is provider-blind: the
    same code serves every adapter. Only ever called on a `tool_use` turn, so
    `parsed.tool_calls` is non-empty and `content` is never empty.
    """
    content: list[dict] = []
    if parsed.text:
        content.append({"type": "text", "text": parsed.text})
    for tc in parsed.tool_calls:
        content.append(
            {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["input"]}
        )
    return {"role": "assistant", "content": content}


def tool_result_message(results: list[dict]) -> dict:
    """The tool-result turn as a `messages` entry.

    `results` is [{"id": str, "content": str, "is_error": bool}].
    """
    content: list[dict] = []
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
