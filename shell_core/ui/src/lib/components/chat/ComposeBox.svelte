<script>
  // Compose area — textarea + send/stop/+chat buttons + token/char counters.
  // `draft` and `inputEl` are bindable so the parent (or the skills popover,
  // through the parent's onCommand handler) can prepend a slash command and
  // focus the textarea.
  //
  // +chat is a two-step destructive action: first click arms (amber glow),
  // second click commits. Stop is intentionally disabled — aborting an
  // in-flight turn needs dispatcher support (flag CC-60).
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

  let clearArmed = $state(false)

  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend() }
  }

  function doSend() {
    if (sending || !shellId || !draft.trim()) return
    onSend?.()
  }

  function handleClearClick() {
    if (!hasMessages) return
    if (clearArmed) { clearArmed = false; onClear?.() }
    else            { clearArmed = true }
  }

  const sendDisabled  = $derived(sending || !shellId || !draft.trim())
  const nearTokenCap  = $derived(contextWindow && chatTokens > contextWindow * 0.9)
  const charNearCap   = $derived(draft.length > MAX_INBOUND_CHARS * 0.8)
  const charAtCap     = $derived(draft.length >= MAX_INBOUND_CHARS)
</script>

<div class="px-4 pt-3 pb-4">
  <!-- caption row — token & char counts -->
  <div class="flex items-center px-2 mb-2 gap-3">
    <span
      class="text-[10px] tabular-nums font-mono {nearTokenCap ? 'text-amber' : 'text-white/40'}"
    >
      {chatTokens.toLocaleString()}{#if contextWindow} / {contextWindow.toLocaleString()}{/if} tok
    </span>
    {#if charNearCap}
      <span
        class="text-[10px] tabular-nums font-mono ml-auto {charAtCap ? 'text-red' : 'text-white/40'}"
      >
        {draft.length.toLocaleString()} / {MAX_INBOUND_CHARS.toLocaleString()}
      </span>
    {/if}
  </div>

  <!-- input pill + vertical action column -->
  <div class="flex items-stretch gap-2">
    <div
      class="flex-1 rounded-2xl border border-white/[0.08] px-4 py-3 flex items-end gap-3"
      style="background: var(--glass-bg-strong);
             backdrop-filter: blur(var(--glass-blur-soft));
             -webkit-backdrop-filter: blur(var(--glass-blur-soft));"
    >
      <textarea
        bind:this={inputEl}
        bind:value={draft}
        onkeydown={onKey}
        placeholder={shellId ? `Message ${shellName}…` : 'No shell assigned'}
        rows="3"
        maxlength={MAX_INBOUND_CHARS}
        disabled={!shellId}
        class="flex-1 bg-transparent border-0 outline-none resize-none
               font-mono text-[12px] leading-snug text-white/90
               placeholder:text-white/40
               disabled:opacity-50"
      ></textarea>
      <button
        onclick={doSend}
        disabled={sendDisabled}
        aria-label="send"
        title="send"
        class="w-8 h-8 rounded-full flex items-center justify-center shrink-0
               text-white/70 hover:text-white hover:bg-white/[0.08] transition
               disabled:opacity-30 disabled:hover:bg-transparent"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor"
          stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <line x1="7" y1="11.5" x2="7" y2="2.5" />
          <polyline points="3,6.5 7,2.5 11,6.5" />
        </svg>
      </button>
    </div>

    <!-- vertical action column -->
    <div class="flex flex-col gap-2 justify-between items-end shrink-0">
      <!-- +chat: two-step confirm. Armed state shows amber glow. -->
      <button
        onclick={handleClearClick}
        disabled={!hasMessages}
        aria-label={clearArmed ? 'click again to confirm new chat' : 'new chat'}
        title={clearArmed ? 'click again to confirm' : 'new chat'}
        class="w-7 h-7 rounded-full border flex items-center justify-center transition-colors duration-200
               disabled:opacity-30
               {clearArmed
                  ? 'border-amber-300/60 text-amber-100'
                  : 'border-white/[0.10] text-white/70'}"
        style="background: {clearArmed ? 'rgba(251,191,36,0.10)' : 'rgba(255,255,255,0.04)'};
               backdrop-filter: blur(var(--glass-blur-soft));
               -webkit-backdrop-filter: blur(var(--glass-blur-soft));
               {clearArmed ? 'box-shadow: 0 0 16px rgba(251,191,36,0.35);' : ''}"
      >
        <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor"
          stroke-width="1.6" stroke-linecap="round">
          <line x1="5.5" y1="2" x2="5.5" y2="9" />
          <line x1="2" y1="5.5" x2="9" y2="5.5" />
        </svg>
      </button>
      <!-- stop: disabled until dispatcher support lands (CC-60). -->
      <button
        disabled
        aria-label="stop"
        title="Stop an in-flight turn — backend not wired yet (CC-60)"
        class="w-7 h-7 rounded-full border border-white/[0.10] text-white/40 flex items-center justify-center
               opacity-40 cursor-default"
        style="background: rgba(255,255,255,0.04);
               backdrop-filter: blur(var(--glass-blur-soft));
               -webkit-backdrop-filter: blur(var(--glass-blur-soft));"
      >
        <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor"
          stroke-width="1.6" stroke-linecap="round">
          <line x1="2.8" y1="2.8" x2="8.2" y2="8.2" />
          <line x1="8.2" y1="2.8" x2="2.8" y2="8.2" />
        </svg>
      </button>
    </div>
  </div>
</div>
