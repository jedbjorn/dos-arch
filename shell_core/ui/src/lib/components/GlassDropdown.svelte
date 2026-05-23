<script>
  // Glass dropdown — shared "pick one of N" trigger + popover. Used by
  // ShellSwitcher (chat header) and the /shells page sub-header.
  //
  // Item shape: { value, label, caption?, suffix? }
  //   - label   : primary text on the row and the trigger (sans, white/90)
  //   - caption : optional secondary text on the row and the trigger
  //               (mono, white/40); read as a shortname / identifier
  //   - suffix  : optional secondary text on the row only (sans, white/40);
  //               read as a tag like "(shared)"
  //
  // Behavior: click trigger to toggle; click a row to select + close;
  // click outside the wrap or press Escape to close.
  let {
    value      = null,
    items      = [],
    onChange,
    disabled   = false,
    orb        = false,   // identity-orb adornment on the trigger (left)
    placeholder = '—',
    align      = 'left',  // 'left' | 'right' — anchors the menu to the trigger edge
  } = $props()

  let open      = $state(false)
  let wrapEl    = $state(null)

  const selected = $derived(items.find(i => i.value === value))

  function toggle() { if (!disabled) open = !open }

  function pick(v) {
    onChange?.(v)
    open = false
  }

  function onWindowClick(e) {
    if (!open) return
    if (wrapEl && wrapEl.contains(e.target)) return
    open = false
  }

  function onKeydown(e) {
    if (e.key === 'Escape' && open) { open = false; e.preventDefault() }
  }
</script>

<svelte:window onclick={onWindowClick} onkeydown={onKeydown} />

<div class="relative" bind:this={wrapEl}>
  <button
    type="button"
    onclick={toggle}
    {disabled}
    class="flex items-center gap-3 group disabled:opacity-50 text-left"
    aria-haspopup="listbox"
    aria-expanded={open}
  >
    {#if orb}
      <div
        class="w-7 h-7 rounded-full shrink-0"
        style="background: var(--orb-grad); box-shadow: 0 0 12px var(--orb-glow);"
      ></div>
    {/if}
    <div class="flex flex-col items-start leading-tight min-w-0">
      <div class="text-sm text-white font-medium truncate">
        {selected?.label ?? placeholder}
      </div>
      {#if selected?.caption}
        <div class="text-[10px] text-white/40 leading-tight mt-0.5 truncate font-mono">
          {selected.caption}
        </div>
      {/if}
    </div>
    <svg
      class="text-white/40 group-hover:text-white/80 transition shrink-0"
      width="10" height="14" viewBox="0 0 10 14" fill="none" stroke="currentColor"
      stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"
    >
      <polyline points="2.5,5 5,2.5 7.5,5" />
      <polyline points="2.5,9 5,11.5 7.5,9" />
    </svg>
  </button>

  {#if open}
    <div
      role="listbox"
      class="absolute top-full mt-2 w-max max-w-[80vw] max-h-96 overflow-y-auto
             rounded-2xl border py-2 z-40
             {align === 'right' ? 'right-0' : 'left-0'}"
      style="background: var(--menu-bg);
             border-color: var(--menu-border);
             box-shadow: var(--menu-shadow);"
    >
      {#each items as it}
        {@const active = it.value === value}
        <button
          type="button"
          role="option"
          aria-selected={active}
          onclick={() => pick(it.value)}
          class="w-full text-left flex flex-col px-4 py-2 transition whitespace-nowrap
                 {active ? 'bg-white/[0.06]' : 'hover:bg-white/[0.04]'}"
        >
          <div class="flex items-baseline gap-2">
            <span class="text-sm text-white/90 flex-1">{it.label}</span>
            {#if it.suffix}
              <span class="text-[10px] text-white/40 shrink-0">{it.suffix}</span>
            {/if}
          </div>
          {#if it.caption}
            <span class="text-[10px] font-mono text-white/40 mt-0.5">{it.caption}</span>
          {/if}
        </button>
      {/each}
    </div>
  {/if}
</div>
