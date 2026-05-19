"""providers — the `ProviderAdapter` seam (agnostic-runtime §3.4).

`get_adapter(provider)` is the single entry point: the dispatcher names a
provider, gets an adapter, and speaks the normalized contract from there on.
`assistant_message` / `tool_result_message` build the normalized next-turn
messages — provider-blind, so they live with the contract, not the adapter.

A1 ships one adapter (Anthropic). A1's later PRs register more; provider
resolution flows from the `models` registry (`models.provider`).
"""

from .anthropic_adapter import AnthropicAdapter
from .base import (
    ParsedResponse,
    ProviderAdapter,
    ProviderError,
    assistant_message,
    tool_result_message,
)

_ADAPTERS: dict[str, type[ProviderAdapter]] = {
    "anthropic": AnthropicAdapter,
}


def get_adapter(provider: str) -> ProviderAdapter:
    """Return a fresh adapter for `provider`. Raises `ValueError` if unknown."""
    try:
        return _ADAPTERS[provider]()
    except KeyError:
        known = ", ".join(sorted(_ADAPTERS)) or "(none)"
        raise ValueError(
            f"no ProviderAdapter for provider '{provider}' — known: {known}"
        ) from None


__all__ = [
    "ParsedResponse",
    "ProviderAdapter",
    "ProviderError",
    "AnthropicAdapter",
    "get_adapter",
    "assistant_message",
    "tool_result_message",
]
