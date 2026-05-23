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

<div class="flex-1 min-h-0 relative flex">
  <div
    bind:this={listEl}
    onscroll={onScroll}
    class="flex-1 overflow-y-auto p-3 flex flex-col gap-2.5 min-h-0"
  >
    {#if messages.length === 0}
      <!-- "ready" empty state — soft accent orb + caption. Mirrors the
           spatial-glass JSX reference's ready-to-chat moment. -->
      <div class="flex-1 flex flex-col items-center justify-center">
        <div
          class="w-16 h-16 rounded-full flex items-center justify-center"
          style="background: var(--orb-soft-grad);
                 box-shadow: 0 0 25px var(--orb-soft-glow);"
        >
          <div class="w-3 h-3 rounded-full bg-white/80"></div>
        </div>
        <div class="text-sm text-white/60 mt-4">ready</div>
      </div>
    {:else}
      {#each messages as msg (msg.message_id)}
        <div class="flex flex-col gap-0.5 {msg.direction === 'outbound' ? 'items-end' : 'items-start'}">
          <div
            class="msg-bubble rounded-2xl px-3.5 py-2 text-[12px] leading-relaxed max-w-[92%] break-words border"
            class:outbound={msg.direction === 'outbound'}
          >
            <MarkdownBlock text={msg.body} />
          </div>
          <div class="text-[9px] font-mono tabular-nums text-white/40 px-1">
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
        <div class="flex items-end self-end px-1 py-1.5">
          <span class="text-[10px] font-mono text-white/40">
            {shellName} is thinking<span class="dots"></span>
          </span>
        </div>
      {/if}

      {#if sendError}
        <div
          class="self-end flex items-center gap-2 px-2.5 py-1.5 rounded-lg border"
          style="background: rgba(224,85,85,0.10); border-color: rgba(224,85,85,0.25);"
        >
          <span class="text-[10px] font-mono text-red">Failed to send</span>
          <button
            onclick={onRetry}
            class="text-[10px] font-mono font-semibold px-2 py-0.5 rounded border border-white/[0.15] text-white/80 hover:text-white hover:border-white/30 transition"
          >Retry</button>
        </div>
      {/if}
    {/if}
  </div>

  {#if !atBottom}
    <button
      onclick={() => scrollToBottom()}
      title="Jump to latest"
      aria-label="Jump to latest"
      class="absolute bottom-3 left-1/2 -translate-x-1/2 w-9 h-9 rounded-full border border-white/[0.10] hover:border-white/[0.20] flex items-center justify-center text-white/60 hover:text-white/90 transition z-[5]"
      style="background: rgba(255,255,255,0.05);
             backdrop-filter: blur(var(--glass-blur-soft));
             -webkit-backdrop-filter: blur(var(--glass-blur-soft));
             box-shadow: 0 4px 24px rgba(0,0,0,0.3);"
    >
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor"
        stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="3.5,5.5 7,9 10.5,5.5" />
      </svg>
    </button>
  {/if}
</div>

<style>
  /* Bubble glass — inbound is the standard glass surface; outbound carries
     a faint accent tint via color-mix so it reads as "yours" without
     fighting the gradient canvas. */
  .msg-bubble {
    background: rgba(255, 255, 255, 0.04);
    border-color: rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.92);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
  }
  .msg-bubble.outbound {
    background: color-mix(in srgb, var(--color-accent) 18%, rgba(255, 255, 255, 0.04));
    border-color: color-mix(in srgb, var(--color-accent) 30%, rgba(255, 255, 255, 0.08));
  }

  .dots::after { content: ''; animation: dots 1.4s steps(4, end) infinite; }
  @keyframes dots {
    0% { content: ''; } 25% { content: '.'; } 50% { content: '..'; }
    75% { content: '...'; } 100% { content: ''; }
  }
</style>
