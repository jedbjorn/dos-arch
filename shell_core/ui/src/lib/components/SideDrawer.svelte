<script>
  // Slide-out left drawer triggered from the hamburger in TopBar.
  // Hosts secondary navigation (config pages) above and the theme
  // selector at the bottom.
  import { goto } from '$app/navigation'
  import { theme, setTheme, THEMES } from '$lib/theme.js'

  let { open = $bindable(false) } = $props()

  // Secondary nav rows — kept in the drawer rather than the TopBar so the
  // bar stays focused on the main surfaces (Shells / Flags / Plans).
  const NAV = [
    { label: 'Ollama Cloud', href: '/ollamacloudconfig' },
  ]

  function go(href) { close(); goto(href) }

  let themeOpen = $state(false)
  let themeWrapEl = $state(null)

  function close() { open = false; themeOpen = false }

  function pickTheme(name) {
    setTheme(name)
    themeOpen = false
  }

  function onWindowClick(e) {
    if (!themeOpen) return
    if (themeWrapEl && themeWrapEl.contains(e.target)) return
    themeOpen = false
  }

  function onKeydown(e) {
    if (e.key === 'Escape' && themeOpen) { themeOpen = false; e.preventDefault() }
  }
</script>

<svelte:window onclick={onWindowClick} onkeydown={onKeydown} />

{#if open}
  <!-- Full-viewport overlay; only the drawer itself catches pointer events,
       so the rest of the app stays interactive (but mouse-leave still fires
       reliably the instant the cursor crosses the drawer's right edge). -->
  <div class="fixed inset-0 z-40 pointer-events-none">
    <aside
      class="absolute left-0 top-0 bottom-0 w-72 pointer-events-auto flex flex-col border-r border-white/[0.08]"
      style="background: rgba(20, 20, 25, 0.85);
             backdrop-filter: blur(24px);
             -webkit-backdrop-filter: blur(24px);"
      onmouseleave={close}
    >
      <div class="px-5 py-4 border-b border-white/[0.08]">
        <div class="text-[10px] tracking-[0.25em] uppercase text-white/40">Options</div>
      </div>

      <div class="flex-1 overflow-y-auto py-2">
        {#each NAV as item}
          <button
            type="button"
            onclick={() => go(item.href)}
            class="w-full text-left px-5 py-2.5 text-[12px] text-white/70 hover:text-white hover:bg-white/[0.05] transition"
          >
            {item.label}
          </button>
        {/each}
      </div>

      <!-- theme selector pinned at bottom -->
      <div class="px-5 py-4 border-t border-white/[0.08]">
        <div class="text-[10px] tracking-[0.25em] uppercase text-white/40 mb-3">Theme</div>
        <div class="relative" bind:this={themeWrapEl}>
          <button
            type="button"
            onclick={() => themeOpen = !themeOpen}
            aria-haspopup="listbox"
            aria-expanded={themeOpen}
            class="theme-row w-full flex items-center pl-4 pr-2.5 py-3 text-left text-[12px] text-white transition rounded-md"
            style="--row-accent: {$theme.accent}; background: {$theme.background};"
          >
            <span class="row-content flex-1 truncate font-medium">{$theme.name}</span>
            <svg
              class="row-content text-white/60 shrink-0 ml-2"
              width="10" height="14" viewBox="0 0 10 14" fill="none" stroke="currentColor"
              stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"
            >
              <polyline points="2.5,5 5,2.5 7.5,5" />
              <polyline points="2.5,9 5,11.5 7.5,9" />
            </svg>
          </button>

          {#if themeOpen}
            <div
              role="listbox"
              class="absolute bottom-full left-0 right-0 mb-2 rounded-2xl border p-2 space-y-1 z-50"
              style="background: var(--menu-bg);
                     border-color: var(--menu-border);
                     box-shadow: var(--menu-shadow);"
            >
              {#each THEMES as t}
                {@const active = $theme.name === t.name}
                <button
                  type="button"
                  role="option"
                  aria-selected={active}
                  onclick={() => pickTheme(t.name)}
                  class="theme-row w-full flex items-center pl-4 pr-2.5 py-3 text-left text-[12px] text-white transition rounded-md
                         {active ? 'is-active' : ''}"
                  style="--row-accent: {t.accent}; background: {t.background};"
                >
                  <span class="row-content flex-1 truncate font-medium">{t.name}</span>
                </button>
              {/each}
            </div>
          {/if}
        </div>
      </div>
    </aside>
  </div>
{/if}

<style>
  .theme-row {
    position: relative;
    overflow: hidden;
    isolation: isolate;
  }
  /* 4px vertical accent bar on the left edge */
  .theme-row::before {
    content: '';
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 4px;
    background: var(--row-accent);
    z-index: 1;
  }
  /* Accent-tinted overlay — hidden by default, revealed on hover / when active */
  .theme-row::after {
    content: '';
    position: absolute;
    inset: 0;
    background: var(--row-accent);
    opacity: 0;
    transition: opacity 0.15s ease;
    pointer-events: none;
    z-index: 1;
  }
  .theme-row:hover::after     { opacity: 0.18; }
  .theme-row.is-active::after { opacity: 0.10; }
  .theme-row:focus-visible    { outline: 1px solid var(--row-accent); outline-offset: -1px; }
  /* Keep inner content above the overlays */
  .theme-row :global(.row-content) { position: relative; z-index: 2; }
</style>
