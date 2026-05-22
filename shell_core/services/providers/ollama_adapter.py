"""ollama_adapter.py — the Ollama `ProviderAdapter` (agnostic-runtime §3.4).

The local-model adapter. Unlike the Anthropic / OpenAI adapters it uses no
vendor SDK — it speaks Ollama's native `/api/chat` over plain HTTP.

Why native `/api/chat` and not Ollama's OpenAI-compatible `/v1` endpoint:
`/v1` gives no way to set the context window per request, so a local model
silently truncates any prompt longer than Ollama's runtime default (~4k
tokens on modest hardware). The conversation history is sent but thrown
away — every turn looks like a fresh chat. `/api/chat` accepts
`options.num_ctx`, so this adapter *owns* the window: it sets `num_ctx` on
every call and trims the prompt to fit, so truncation is dos-arch's
decision, never a silent surprise.

── Context window — `OLLAMA_NUM_CTX` ──────────────────────────────────────
`num_ctx` is read once from the `OLLAMA_NUM_CTX` env var (default 16384) and
sent on every request. It is the KV-cache size Ollama allocates: raise it on
a big-VRAM host, lower it on a constrained one. Ollama clamps it down to a
model's own trained maximum automatically, so one host-wide value is safe
across every local model. The adapter then trims message history so
`system + history + reply reserve` fits inside `num_ctx`, so Ollama itself
never has to truncate.

── Model residency — `OLLAMA_KEEP_ALIVE` ──────────────────────────────────
`keep_alive` is read once from `OLLAMA_KEEP_ALIVE` (default `1h`) and sent on
every request. It controls how long Ollama keeps the model — and its KV
cache — resident in VRAM after a turn. Ollama's own default is 5 minutes,
which any user pause exceeds: the model unloads and the next turn pays a
cold reload plus a full prefill. A longer value keeps the warm prefix cache
alive between turns; `-1` pins the model indefinitely on a big-VRAM host.

── Wire format ─────────────────────────────────────────────────────────────
Native `/api/chat` differs structurally from the normalized (Anthropic-
shaped) contract in `base.py`:
  - `system` is a message (`role:"system"`), not a separate field;
  - an assistant turn carries tool calls in a `tool_calls` array whose
    `function.arguments` is a JSON *object* (OpenAI sends a string);
  - each tool result is its own `role:"tool"` message;
  - tool calls have no id — Ollama pairs results by `tool_name`. This adapter
    synthesizes ids for the normalized contract and resolves them back to
    names when projecting the next request.

`cost()` returns 0.0 — local models have no per-token dollar cost.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

from .base import ParsedResponse, ProviderAdapter, ProviderError

_DEFAULT_BASE       = "http://localhost:11434"
_DEFAULT_NUM_CTX    = 16384
_DEFAULT_KEEP_ALIVE = "1h"   # how long Ollama keeps the model resident in VRAM
_CHARS_PER_TOKEN    = 4      # rough token estimate, used only for history trimming
_OUTPUT_RESERVE     = 2048   # tokens kept free inside num_ctx for the reply
_TIMEOUT            = 600    # seconds — local generation can be slow

# Ollama `done_reason` -> normalized stop_reason (see base.py vocabulary). A
# tool-call turn also reports "stop", so tool_calls presence is checked first
# in parse_response; this map only covers the no-tool case.
_STOP_REASON = {"stop": "end_turn", "length": "max_tokens"}


class OllamaAdapter(ProviderAdapter):
    """Ollama's native `/api/chat` endpoint behind the normalized seam."""

    provider = "local"

    def __init__(self, endpoint: str | None = None) -> None:
        base = (endpoint or os.environ.get("OLLAMA_API_BASE") or _DEFAULT_BASE).rstrip("/")
        # Tolerate an OpenAI-compat URL (…/v1) from a registry row written
        # before the native-endpoint switch — the native API is at the bare base.
        if base.endswith("/v1"):
            base = base[:-3].rstrip("/")
        self._base = base
        self._chat_url = base + "/api/chat"
        try:
            self._num_ctx = int(os.environ.get("OLLAMA_NUM_CTX", _DEFAULT_NUM_CTX))
        except ValueError:
            self._num_ctx = _DEFAULT_NUM_CTX
        self._keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", _DEFAULT_KEEP_ALIVE)

    # ── token estimation + history trimming ──────────────────────────────────

    @staticmethod
    def _est(text: str) -> int:
        return len(text) // _CHARS_PER_TOKEN + 1

    @staticmethod
    def _msg_tokens(msg: dict) -> int:
        content = msg.get("content", "")
        text = content if isinstance(content, str) else json.dumps(content)
        return OllamaAdapter._est(text)

    def _trim(self, messages: list, system_text: str) -> list:
        """Keep the newest messages that fit alongside the system prompt.

        Budget = num_ctx − system − reply reserve. Walks newest-first, always
        keeps the last message, then drops any leading non-user turn so the
        request opens cleanly on a user message.
        """
        budget = self._num_ctx - self._est(system_text) - _OUTPUT_RESERVE
        if budget <= 0:
            print(
                f"[ollama_adapter] WARNING: system prompt (~{self._est(system_text)} "
                f"tok) does not fit num_ctx={self._num_ctx} — raise OLLAMA_NUM_CTX. "
                f"Sending only the latest message.",
                file=sys.stderr, flush=True,
            )
            return messages[-1:]
        kept: list = []
        running = 0
        for m in reversed(messages):
            t = self._msg_tokens(m)
            if kept and running + t > budget:
                break
            kept.append(m)
            running += t
        kept.reverse()
        # Ollama is happiest when the first non-system message is a user turn.
        while kept and kept[0]["role"] != "user":
            kept.pop(0)
        return kept or messages[-1:]

    # ── normalized -> native message translation ─────────────────────────────

    @staticmethod
    def _native_messages(messages: list) -> list:
        """Normalized messages -> Ollama `/api/chat` messages.

        Assistant tool-use blocks collapse into a `tool_calls` array (arguments
        as a JSON object); a tool-result turn fans out into one `role:"tool"`
        message each, tagged with the tool name resolved from the synthesized id.
        """
        id_to_name = {
            b["id"]: b["name"]
            for m in messages
            if m["role"] == "assistant" and isinstance(m["content"], list)
            for b in m["content"]
            if b.get("type") == "tool_use"
        }
        out: list = []
        for m in messages:
            role, content = m["role"], m["content"]
            if isinstance(content, str):
                out.append({"role": role, "content": content})
                continue
            if role == "assistant":
                text = "\n".join(b["text"] for b in content if b["type"] == "text")
                tool_calls = [
                    {"function": {"name": b["name"], "arguments": b["input"]}}
                    for b in content if b["type"] == "tool_use"
                ]
                msg = {"role": "assistant", "content": text}
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                out.append(msg)
            else:
                # A user-role turn carrying tool_result blocks — each becomes
                # its own role:"tool" message, keyed back to the tool name.
                for b in content:
                    if b["type"] == "tool_result":
                        tm = {"role": "tool", "content": b["content"]}
                        name = id_to_name.get(b["tool_use_id"])
                        if name:
                            tm["tool_name"] = name
                        out.append(tm)
        return out

    # ── ProviderAdapter contract ─────────────────────────────────────────────

    def format_request(
        self,
        system_blocks: list,
        tools: list,
        messages: list,
        model: str,
        max_tokens: int,
    ) -> dict:
        # System blocks split by the normalized `cache` flag (base.py). The
        # cacheable blocks (the boot document) lead as one system message — a
        # stable prefix Ollama's runner reuses turn to turn. The volatile
        # blocks (Block 3, the live tail) fold into the latest user turn
        # instead: Ollama prefix-caches from token 0, so a block that changes
        # every turn, sitting in the system prefix, would cap the reusable
        # prefix at the boot document and re-prefill the whole conversation
        # history every turn. Trailing it keeps boot + history cacheable.
        cacheable = [b["text"] for b in system_blocks if b.get("cache")]
        volatile = [b["text"] for b in system_blocks if not b.get("cache")]
        cacheable_text = "\n\n".join(cacheable)
        volatile_text = "\n\n".join(volatile)
        num_predict = min(max_tokens, self._num_ctx)

        # Trim against the full system overhead — both parts occupy context
        # even when placed in different positions.
        parts = [p for p in (cacheable_text, volatile_text) if p]
        system_text = "\n\n".join(parts)

        native: list[dict] = []
        if cacheable_text:
            native.append({"role": "system", "content": cacheable_text})
        native.extend(self._native_messages(self._trim(messages, system_text)))

        # Fold the volatile tail into the last user turn — it still reaches
        # the model this turn but stays out of the cached prefix. With no user
        # turn (not a real conversation shape), fall back to the leading
        # system block so the live state is never silently dropped.
        if volatile_text:
            last_user = next(
                (m for m in reversed(native) if m["role"] == "user"), None)
            if last_user is not None:
                last_user["content"] = f"{volatile_text}\n\n{last_user['content']}"
            elif native and native[0]["role"] == "system":
                native[0]["content"] = f"{native[0]['content']}\n\n{volatile_text}"
            else:
                native.insert(0, {"role": "system", "content": volatile_text})

        request = {
            "model": model,
            "messages": native,
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {"num_ctx": self._num_ctx, "num_predict": num_predict},
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
        data = json.dumps(request).encode()
        last_err = "unknown error"
        for attempt in range(3):
            if attempt:
                time.sleep(0.5 * (2 ** attempt))   # 1s, 2s
            try:
                req = urllib.request.Request(
                    self._chat_url, data=data, method="POST",
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")[:500]
                # 5xx can be transient (model still loading); 4xx will not be.
                if e.code >= 500 and attempt < 2:
                    last_err = f"HTTP {e.code}: {body}"
                    continue
                raise ProviderError(f"Ollama HTTP {e.code}: {body}") from e
            except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                last_err = f"{type(e).__name__}: {e}"
                if attempt < 2:
                    continue
                raise ProviderError(
                    f"Ollama unreachable at {self._chat_url}: {last_err}") from e
        raise ProviderError(f"Ollama call failed: {last_err}")

    def parse_response(self, response) -> ParsedResponse:
        message = response.get("message") or {}
        text = (message.get("content") or "").strip()

        tool_calls = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            # Ollama tool calls carry no id — synthesize one so the normalized
            # contract (assistant_message / tool_result_message) can pair them.
            tool_calls.append({
                "id": f"ollama-{uuid.uuid4().hex[:12]}",
                "name": fn.get("name", ""),
                "input": args or {},
            })

        usage = {
            "input_tokens":  response.get("prompt_eval_count") or 0,
            "output_tokens": response.get("eval_count") or 0,
        }
        # done_reason reads "stop" even on a tool-call turn — tool_calls
        # presence is the real signal, so it wins.
        stop_reason = (
            "tool_use" if tool_calls
            else _STOP_REASON.get(response.get("done_reason"), "end_turn")
        )
        return ParsedResponse(text=text, tool_calls=tool_calls,
                              usage=usage, stop_reason=stop_reason)

    def cost(self, usage: dict, model: str) -> float:
        # Local models have no per-token dollar cost. Completes the seam
        # interface; the dispatcher is tokens-only anyway (decision #108).
        return 0.0
