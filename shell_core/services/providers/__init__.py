"""providers — the `ProviderAdapter` seam (agnostic-runtime §3.4).

`get_adapter(provider, **kwargs)` is the single entry point: the dispatcher
names a provider, gets an adapter, and speaks the normalized contract from
there on. `assistant_message` / `tool_result_message` build the normalized
next-turn messages — provider-blind, so they live with the contract, not
the adapter.

A1 ships Anthropic + OpenAI. CC-51 adds Ollama (the `local` provider); it
speaks Ollama's native `/api/chat`, which lets it own the context window
(`num_ctx`) instead of letting the model truncate the prompt silently.
The `ollama_cloud` provider extends that same native protocol to
Ollama's hosted service — same wire shape, bearer-token auth, no local
trimming. Provider resolution flows from the `models` registry
(`models.provider` + `models.endpoint`).
"""

from .anthropic_adapter import AnthropicAdapter
from .base import (
    ParsedResponse,
    ProviderAdapter,
    ProviderError,
    assistant_message,
    tool_result_message,
)
from .ollama_adapter import OllamaAdapter
from .ollama_cloud_adapter import OllamaCloudAdapter
from .openai_adapter import OpenAIAdapter

_ADAPTERS: dict[str, type[ProviderAdapter]] = {
    "anthropic":    AnthropicAdapter,
    "openai":       OpenAIAdapter,
    "local":        OllamaAdapter,
    "ollama_cloud": OllamaCloudAdapter,
}


def get_adapter(provider: str, **kwargs) -> ProviderAdapter:
    """Return a fresh adapter for `provider`. `endpoint=...` is honored by
    adapters that vary by host (`local` and `ollama_cloud`); the cloud
    adapters that don't vary by host accept it for interface uniformity
    and ignore it."""
    try:
        cls = _ADAPTERS[provider]
    except KeyError:
        known = ", ".join(sorted(_ADAPTERS)) or "(none)"
        raise ValueError(
            f"no ProviderAdapter for provider '{provider}' — known: {known}"
        ) from None
    return cls(**kwargs)


__all__ = [
    "ParsedResponse",
    "ProviderAdapter",
    "ProviderError",
    "AnthropicAdapter",
    "OpenAIAdapter",
    "OllamaAdapter",
    "OllamaCloudAdapter",
    "get_adapter",
    "assistant_message",
    "tool_result_message",
]
