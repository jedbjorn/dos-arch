<script>
  // Available-models column — providers grouped, click a row to switch the
  // current conversation's pinned model. Parent's onChange takes the
  // selected model_id as a string ('' = none pinned).
  import { PROVIDERS, modelsByProvider, modelLabel } from '$lib/chat/models.js'

  let { models = [], selectedModel = '', onChange } = $props()
  const grouped = $derived(modelsByProvider(models))
  const totalCount = $derived(models.length)
</script>

<div class="w-[180px] shrink-0 flex flex-col border-r border-white/[0.08]">
  <div class="h-[52px] flex flex-col justify-center px-5 border-b border-white/[0.06]">
    <div class="text-sm text-white font-medium leading-tight">Models</div>
    <div class="text-[10px] text-white/40 leading-tight mt-0.5 tabular-nums">
      {totalCount} available
    </div>
  </div>
  <div class="flex-1 overflow-y-auto p-4">
    {#each PROVIDERS as p}
      <div class="mb-5">
        <div class="text-[10px] uppercase tracking-[0.15em] text-white/30 mb-2">{p.label}</div>
        <div class="space-y-1">
          {#each grouped[p.key] ?? [] as m}
            {@const active = String(m.model_id) === selectedModel}
            <button
              onclick={() => onChange(String(m.model_id))}
              class="w-full text-left px-3 py-2 text-[11px] font-mono transition leading-snug break-words
                     {active
                        ? 'active-row'
                        : 'text-white/60 hover:text-white/90 hover:bg-white/[0.03]'}"
            >
              {modelLabel(m)}
            </button>
          {/each}
          {#if !(grouped[p.key] ?? []).length}
            <div class="px-3 py-1 text-[10px] italic text-white/30">(none yet)</div>
          {/if}
        </div>
      </div>
    {/each}
  </div>
</div>
