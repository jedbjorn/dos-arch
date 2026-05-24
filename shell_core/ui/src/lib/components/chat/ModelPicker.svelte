<script>
  // Available-models column — providers grouped, click a row to switch the
  // current conversation's pinned model. Parent's onChange takes the
  // selected model_id as a string ('' = none pinned).
  //
  // Local rows carry a kebab menu (3-dot) that opens a "Move to agents"
  // action: hides the row from the picker by flipping its registry
  // accepts_substrate_system bit. Surfaced for the hermes-class case where
  // the static template classifier can't catch a model that drops the
  // boot prompt under tools. Parent handles the API call + reload via
  // onRouteToAgents(model_id).
  import { PROVIDERS, modelsByProvider, modelLabel } from '$lib/chat/models.js'

  let {
    models = [], selectedModel = '', onChange, onRouteToAgents,
  } = $props()
  const grouped = $derived(modelsByProvider(models))
  const totalCount = $derived(models.length)

  let menuOpenFor = $state(null)   // model_id whose kebab popover is open

  function toggleMenu(model_id, e) {
    e.stopPropagation()
    menuOpenFor = menuOpenFor === model_id ? null : model_id
  }

  function onWindowClick(e) {
    if (menuOpenFor === null) return
    // Any element flagged data-model-menu (the kebab button or the menu
    // popover itself) keeps the menu open; clicking elsewhere closes it.
    // `closest()` walks up the DOM so the click can land anywhere inside
    // the popover content too.
    if (e.target.closest?.('[data-model-menu]')) return
    menuOpenFor = null
  }

  function onKeydown(e) {
    if (e.key === 'Escape' && menuOpenFor !== null) {
      menuOpenFor = null
      e.preventDefault()
    }
  }

  async function demote(model_id) {
    menuOpenFor = null
    await onRouteToAgents?.(model_id)
  }
</script>

<svelte:window onclick={onWindowClick} onkeydown={onKeydown} />

<div class="w-[180px] shrink-0 flex flex-col border-r border-white/[0.08]">
  <div class="h-[52px] flex flex-col justify-center px-5 border-b border-white/[0.06]">
    <div class="text-sm text-white font-medium leading-tight">Models</div>
    <div class="text-[10px] text-white/40 leading-tight mt-0.5 tabular-nums">
      {totalCount} available
    </div>
  </div>
  <div class="flex-1 overflow-y-auto py-4 px-2">
    {#each PROVIDERS as p}
      <div class="mb-5">
        <div class="text-[10px] uppercase tracking-[0.15em] text-white/30 mb-2">{p.label}</div>
        <div class="space-y-1">
          {#each grouped[p.key] ?? [] as m}
            {@const active = String(m.model_id) === selectedModel}
            <div class="relative group flex items-stretch">
              <button
                onclick={() => onChange(String(m.model_id))}
                class="flex-1 min-w-0 text-left pl-2 pr-1 py-2 text-[11px] font-mono transition leading-snug break-words
                       {active
                          ? 'active-row'
                          : 'text-white/60 hover:text-white/90 hover:bg-white/[0.03]'}"
              >
                {modelLabel(m)}
              </button>
              {#if p.key === 'local'}
                <button
                  type="button"
                  aria-label="Model options"
                  data-model-menu
                  onclick={(e) => toggleMenu(m.model_id, e)}
                  class="px-2 opacity-0 group-hover:opacity-100 transition text-white/40 hover:text-white/80
                         {menuOpenFor === m.model_id ? 'opacity-100' : ''}"
                >
                  <svg width="3" height="13" viewBox="0 0 3 13" fill="currentColor" aria-hidden="true">
                    <circle cx="1.5" cy="1.5"  r="1.2"/>
                    <circle cx="1.5" cy="6.5"  r="1.2"/>
                    <circle cx="1.5" cy="11.5" r="1.2"/>
                  </svg>
                </button>
                {#if menuOpenFor === m.model_id}
                  <div
                    role="menu"
                    data-model-menu
                    class="absolute right-0 top-full mt-1 min-w-[140px] rounded-md border py-1 z-40"
                    style="background: var(--menu-bg);
                           border-color: var(--menu-border);
                           box-shadow: var(--menu-shadow);"
                  >
                    <button
                      type="button"
                      role="menuitem"
                      onclick={() => demote(m.model_id)}
                      class="w-full text-left px-3 py-1.5 text-[11px] text-white/80 hover:text-white hover:bg-white/[0.05] transition"
                    >
                      Move to agents
                    </button>
                  </div>
                {/if}
              {/if}
            </div>
          {/each}
          {#if !(grouped[p.key] ?? []).length}
            <div class="px-3 py-1 text-[10px] italic text-white/30">(none yet)</div>
          {/if}
        </div>
      </div>
    {/each}
  </div>
</div>
