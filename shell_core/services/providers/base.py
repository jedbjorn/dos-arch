"""base.py — the `ProviderAdapter` seam (agnostic-runtime §3.4).

The dispatcher thinks in one normalized vocabulary — "system blocks, a tool
list, a message list, a tool-use loop until end_turn." Each adapter projects
that vocabulary onto its provider's wire format. Every provider-specific
import, type, and exception lives behind this interface; the dispatcher loop
never names a provider.

The normalized contract:

    format_request(system_blocks, tools, messages, model, max_tokens)
        -> native request          (whatever `call` consumes)
    call(request)
        -> native response         (whatever `parse_response` consumes)
    parse_response(response)
        -> ParsedResponse           (text, tool_calls, usage, stop_reason)
    cost(usage, model)
        -> float (USD)

Plus two message-shaping helpers — the assistant turn and the tool-result
turn must be echoed back in the provider's own wire format, so the adapter
owns their construction too:

    serialize_assistant(response)   -> a message dict to append to `messages`
    serialize_tool_results(results) -> a message dict to append to `messages`

`messages` stays in the provider's native shape between turns; `format_request`
is where it is (re)projected. With one adapter (A0) that projection is an
identity; A1 onward it does real translation.

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

    @abstractmethod
    def serialize_assistant(self, response) -> dict:
        """The assistant turn (text + tool_use), as a `messages` entry."""

    @abstractmethod
    def serialize_tool_results(self, results: list[dict]) -> dict:
        """The tool-result turn, as a `messages` entry.

        `results` is [{"id": str, "content": str, "is_error": bool}].
        """
