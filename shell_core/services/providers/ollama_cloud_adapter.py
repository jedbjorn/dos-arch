"""ollama_cloud_adapter.py — Ollama Cloud `ProviderAdapter` (agnostic-runtime §3.4).

Ollama Cloud speaks the same native `/api/chat` protocol as a self-hosted
Ollama daemon — only the host (`https://ollama.com`) and a bearer-token
Authorization header differ. So this adapter is a thin subclass of
`OllamaAdapter`: it inherits format_request, _native_messages, and
parse_response wholesale, and overrides only the bits that diverge.

── Auth — broker-injected, or `OLLAMA_CLOUD_API_KEY` direct ─────────────────
Two transports, chosen at construction by whether `BROKER_BASE` is set (the
same seam the anthropic/openai adapters use):

  • Broker mode (BROKER_BASE set — the credential-free dispatcher): the chat
    URL targets the broker's `/ollama_cloud` prefix and the request carries
    NO key; the broker injects `Authorization: Bearer` on egress from its
    encrypted store. The shell process never holds the key.
  • Direct mode (host CLI / no broker): the key is read at call time from the
    env var named by the model row's `auth_ref` (default `OLLAMA_CLOUD_API_KEY`)
    and attached here. Missing key raises `ProviderError` at call time — not
    construction — so the dispatcher surfaces a clean per-turn error.

── Trimming ────────────────────────────────────────────────────────────────
The parent's `_trim` is designed around a local box's finite VRAM
(OLLAMA_NUM_CTX, default 16k). Cloud models carry their own large windows
(gpt-oss:120b is 131k); the dispatcher already bounds conversation growth
elsewhere, and the server will 4xx if a request truly overruns. So `_trim`
is overridden to a no-op — pass the full history through.

`cost()` returns 0.0 for now (tokens-only billing per decision #108). Per-
model pricing can be wired in later from the registry's cost_* columns.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from .base import ProviderError
from .ollama_adapter import OllamaAdapter

_DEFAULT_BASE     = "https://ollama.com"
_DEFAULT_AUTH_REF = "OLLAMA_CLOUD_API_KEY"
_TIMEOUT          = 600


class OllamaCloudAdapter(OllamaAdapter):
    """Ollama Cloud's native `/api/chat` endpoint behind the normalized seam."""

    provider = "ollama_cloud"

    def __init__(self, endpoint: str | None = None, auth_ref: str | None = None) -> None:
        # Resolve base + URL the same way the parent does, but point at the
        # cloud host by default. Tolerate a trailing /v1 just in case a row
        # was authored against the OpenAI-compat URL.
        base = (endpoint or _DEFAULT_BASE).rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3].rstrip("/")
        self._base = base
        self._auth_ref = auth_ref or _DEFAULT_AUTH_REF
        # Broker mode: route the native /api/chat call through the credential
        # broker's /ollama_cloud prefix (it injects the bearer token on egress);
        # the dispatcher holds no key. Direct mode: hit the cloud host and add
        # the key from the env in call(). Mirrors remote_model_sync's transport.
        broker = os.environ.get("BROKER_BASE")
        self._via_broker = bool(broker)
        if broker:
            self._chat_url = f"{broker.rstrip('/')}/ollama_cloud/api/chat"
        else:
            self._chat_url = base + "/api/chat"
        # num_ctx is inherited from the parent for interface uniformity (the
        # `options` block in format_request still sets it) but _trim is a
        # no-op here, so it never gates the history.
        self._num_ctx = 131072
        self._keep_alive = "1h"

    # ── trimming: no-op for cloud ────────────────────────────────────────────

    def _trim(self, messages: list, system_text: str) -> list:
        return messages

    # ── call: same wire shape; bearer auth only in direct mode ───────────────

    def call(self, request: dict):
        data = json.dumps(request).encode()
        headers = {"Content-Type": "application/json"}
        if not self._via_broker:
            # Direct mode: attach the bearer token ourselves. In broker mode the
            # broker injects Authorization on egress, so we send none.
            api_key = os.environ.get(self._auth_ref)
            if not api_key:
                raise ProviderError(
                    f"Ollama Cloud key not set — expected env var {self._auth_ref}")
            headers["Authorization"] = f"Bearer {api_key}"
        last_err = "unknown error"
        for attempt in range(3):
            if attempt:
                time.sleep(0.5 * (2 ** attempt))
            try:
                req = urllib.request.Request(
                    self._chat_url, data=data, method="POST", headers=headers)
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")[:500]
                if e.code >= 500 and attempt < 2:
                    last_err = f"HTTP {e.code}: {body}"
                    continue
                raise ProviderError(f"Ollama Cloud HTTP {e.code}: {body}") from e
            except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                last_err = f"{type(e).__name__}: {e}"
                if attempt < 2:
                    continue
                raise ProviderError(
                    f"Ollama Cloud unreachable at {self._chat_url}: {last_err}"
                ) from e
        raise ProviderError(f"Ollama Cloud call failed: {last_err}")
