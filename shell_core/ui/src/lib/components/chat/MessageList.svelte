<script>
  // Message list + waiting indicator + send-error retry + jump-to-bottom.
  // Owns the scroll container. Exposes `atBottom` (bindable) so the parent's
  // poll can decide whether to follow new content, and `scrollToBottom`
  // (bindable function) so the parent can yank to the latest message after
  // send / shell switch / init.
  import MarkdownBlock from '../MarkdownBlock.svelte'

  let {
    messages = [],
    waiting = false,
    sendError = false,
    shellName = 'Shell',
    onRetry,
    atBottom = $bindable(true),
    scrollToBottom = $bindable(() => {}),
  } = $props()

  let listEl = $state(null)

  // Expose the scroll action up so the parent can call it after send / etc.
  $effect(() => {
    scrollToBottom = () => {
      if (listEl) listEl.scrollTop = listEl.scrollHeight
      atBottom = true
    }
  })

  // A reader scrolled up into backscroll must not get yanked down on the
  // next poll. Re-anchor only when within 60px of the bottom.
  function onScroll() {
    if (!listEl) return
    atBottom = listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight < 60
  }
</script>

<div class="list-wrap">
  <div class="messages" bind:this={listEl} onscroll={onScroll}>
    {#if messages.length === 0}
      <div class="empty">No messages yet.</div>
    {:else}
      {#each messages as msg (msg.message_id)}
        <div class="msg" class:outbound={msg.direction === 'outbound'}>
          <div class="bubble"><MarkdownBlock text={msg.body} /></div>
          <div class="meta">
            {msg.sent_at?.slice(0, 16).replace('T', ' ')}
            {#if msg.direction === 'outbound' && msg.tokens != null}
              &nbsp;{msg.tokens.toLocaleString()} tok
            {:else if msg.direction === 'inbound'}
              &nbsp;~{Math.ceil((msg.body?.length ?? 0) / 4).toLocaleString()} tok
            {/if}
          </div>
        </div>
      {/each}

      {#if waiting}
        <div class="waiting">
          <span class="waiting-label">{shellName} is thinking<span class="dots"></span></span>
        </div>
      {/if}

      {#if sendError}
        <div class="send-error">
          <span class="error-msg">Failed to send</span>
          <button class="retry-btn" onclick={onRetry}>Retry</button>
        </div>
      {/if}
    {/if}
  </div>

  {#if !atBottom}
    <button class="jump-btn" onclick={() => scrollToBottom()} title="Jump to latest" aria-label="Jump to latest">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M5 9l7 7 7-7" />
      </svg>
    </button>
  {/if}
</div>

<style>
  /* Wraps the list so the jump-button can anchor absolutely above the
     compose area without bleeding outside the chat column. */
  .list-wrap { flex: 1; min-height: 0; position: relative; display: flex; }

  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 0;
  }
  .empty { color: var(--color-text-dim); font-size: 12px; text-align: center; margin-top: 40px; }

  .msg { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; }
  .msg.outbound { align-items: flex-end; }
  .bubble {
    background: var(--color-surface-2);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 12px;
    color: var(--color-text);
    max-width: 92%;
    word-break: break-word;
    line-height: 1.5;
  }
  .msg.outbound .bubble {
    background: color-mix(in srgb, var(--color-accent) 15%, var(--color-surface-1));
    border-color: color-mix(in srgb, var(--color-accent) 30%, var(--color-border));
  }
  .meta { font-family: var(--font-mono); font-size: 9px; color: var(--color-text-dim); padding: 0 2px; }

  .waiting { display: flex; align-items: flex-end; padding: 6px 2px; align-self: flex-end; }
  .waiting-label { font-family: var(--font-mono); font-size: 9px; color: var(--color-text-dim); }
  .dots::after { content: ''; animation: dots 1.4s steps(4, end) infinite; }
  @keyframes dots {
    0% { content: ''; } 25% { content: '.'; } 50% { content: '..'; }
    75% { content: '...'; } 100% { content: ''; }
  }

  .send-error {
    display: flex; align-items: center; gap: 8px; align-self: flex-end;
    padding: 5px 10px; border-radius: 6px;
    background: rgba(224,85,85,0.08);
    border: 1px solid rgba(224,85,85,0.2);
  }
  .error-msg  { font-family: var(--font-mono); font-size: 10px; color: var(--color-red); }
  .retry-btn  {
    font-family: var(--font-mono); font-size: 10px; font-weight: 600;
    background: none; border: 1px solid var(--color-accent); border-radius: 4px;
    color: var(--color-accent); cursor: pointer; padding: 2px 8px;
  }
  .retry-btn:hover { background: rgba(0,114,255,0.08); }

  .jump-btn {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    bottom: 12px;
    width: 34px; height: 34px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer;
    color: #fff;
    background: var(--color-surface-1);
    border: 1px solid var(--color-border);
    box-shadow: 0 2px 12px rgba(0,0,0,0.55);
    z-index: 5;
  }
  .jump-btn svg { width: 20px; height: 20px; display: block; }
  .jump-btn:hover { background: var(--color-surface-2); }
</style>
