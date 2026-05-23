<script>
  // Compose area — textarea + stop/clear/send buttons + token/char counters.
  // `draft` and `inputEl` are bindable so the parent (or the skills popover,
  // through the parent's onCommand handler) can prepend a slash command and
  // focus the textarea.
  //
  // Stop button is intentionally disabled — aborting an in-flight turn
  // needs dispatcher support (flag CC-60).
  import { MAX_INBOUND_CHARS } from '$lib/chat/tokens.js'

  let {
    shellId = null,
    shellName = 'Shell',
    sending = false,
    hasMessages = false,
    chatTokens = 0,
    contextWindow = null,
    onSend,
    onClear,
    draft = $bindable(''),
    inputEl = $bindable(null),
  } = $props()

  let clearConfirm = $state(false)

  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend?.() }
  }

  function confirmClear() { clearConfirm = false; onClear?.() }
</script>

<div class="compose">
  <textarea
    class="input"
    bind:this={inputEl}
    placeholder={shellId ? `Message ${shellName}…` : 'No shell assigned'}
    rows="3"
    bind:value={draft}
    onkeydown={onKey}
    maxlength={MAX_INBOUND_CHARS}
    disabled={!shellId}
  ></textarea>
  <div class="compose-btns">
    <button class="cbtn stop" disabled
      title="Stop an in-flight turn — backend not wired yet (CC-60)">stop</button>
    {#if clearConfirm}
      <!-- Inline confirm — +chat ends the current conversation. -->
      <div class="clear-inline">
        <button class="cbtn confirm-clear" onclick={confirmClear}>confirm</button>
        <button class="cbtn cancel-clear" onclick={() => clearConfirm = false}>✕</button>
      </div>
    {:else}
      <button class="cbtn clear" onclick={() => clearConfirm = true}
        disabled={!hasMessages}>+chat</button>
    {/if}
    <button class="cbtn send" onclick={() => onSend?.()}
      disabled={sending || !shellId || !draft.trim()}>send</button>
  </div>
</div>
<div class="compose-meta">
  <span class="token-count"
    class:near-cap={contextWindow && chatTokens > contextWindow * 0.9}>
    {chatTokens.toLocaleString()}{#if contextWindow} / {contextWindow.toLocaleString()}{/if} tok
  </span>
  {#if draft.length > MAX_INBOUND_CHARS * 0.8}
    <span class="char-count" class:at-cap={draft.length >= MAX_INBOUND_CHARS}>
      {draft.length.toLocaleString()} / {MAX_INBOUND_CHARS.toLocaleString()}
    </span>
  {/if}
</div>

<style>
  .compose {
    display: flex;
    gap: 8px;
    padding: 8px 12px;
    background: var(--color-surface-2);
    border-top: 1px solid var(--color-border);
  }
  .input {
    flex: 1;
    background: var(--color-surface-1);
    border: 1px solid var(--color-border);
    border-radius: 6px;
    color: var(--color-text);
    font-family: var(--font-mono);
    font-size: 12px;
    padding: 6px 8px;
    resize: none;
    line-height: 1.4;
  }
  .input:focus { outline: none; border-color: var(--color-accent); }

  .compose-btns {
    display: flex; flex-direction: column;
    gap: 4px;
    justify-content: flex-end; align-items: flex-end;
  }
  .cbtn {
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.04em;
    border-radius: 4px;
    padding: 3px 10px;
    cursor: pointer;
    border: 1px solid var(--color-border);
    background: var(--color-surface-1);
    color: var(--color-text-dim);
  }
  .cbtn:disabled { opacity: 0.4; cursor: default; }
  .cbtn.send:not(:disabled) { border-color: var(--color-accent); color: var(--color-accent); }
  .cbtn.send:not(:disabled):hover { background: rgba(0,114,255,0.08); }
  .cbtn.clear:not(:disabled):hover { border-color: var(--color-red); color: var(--color-red); }

  .clear-inline { display: flex; gap: 4px; justify-content: flex-end; }
  .cbtn.confirm-clear { border-color: var(--color-red); color: var(--color-red); }
  .cbtn.confirm-clear:hover { background: rgba(224,85,85,0.12); }
  .cbtn.cancel-clear { padding: 3px 8px; }

  .compose-meta {
    display: flex;
    justify-content: space-between; gap: 8px;
    padding: 2px 12px 6px;
    background: var(--color-surface-2);
  }
  .token-count { font-family: var(--font-mono); font-size: 9px; color: var(--color-text-dim); }
  .token-count.near-cap { color: var(--color-amber); }
  .char-count { font-family: var(--font-mono); font-size: 9px; color: var(--color-text-dim); margin-left: auto; }
  .char-count.at-cap { color: var(--color-red); }
</style>
