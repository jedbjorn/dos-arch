"""providers — the `ProviderAdapter` seam (agnostic-runtime §3.4).

`get_adapter(provider)` is the single entry point: the dispatcher names a
provider, gets an adapter, and speaks the normalized contract from there on.

A0 ships one adapter (Anthropic). A1 onward registers more; provider
resolution then flows from the `models` registry (`models.provider`) rather
than a hard-coded string.
"""

from .anthropic_adapter import AnthropicAdapter
from .base import ParsedResponse, ProviderAdapter, ProviderError

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
]
