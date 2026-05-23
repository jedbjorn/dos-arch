<script>
  // Slide-out left drawer triggered from the hamburger in TopBar.
  // Currently stashes the theme selector; the body above is reserved
  // for future switching options (account, layout, etc.).
  import { theme, setTheme, THEMES } from '$lib/theme.js'

  let { open = $bindable(false) } = $props()

  function close() { open = false }
</script>

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

      <!-- placeholder for future switching options -->
      <div class="flex-1 overflow-y-auto"></div>

      <!-- theme selector pinned at bottom -->
      <div class="px-5 py-4 border-t border-white/[0.08]">
        <div class="text-[10px] tracking-[0.25em] uppercase text-white/40 mb-3">Theme</div>
        <div class="space-y-1">
          {#each THEMES as t}
            {@const active = $theme.name === t.name}
            <button
              onclick={() => setTheme(t.name)}
              class="w-full flex items-center gap-3 px-2.5 py-2 text-left text-[12px] transition
                     {active
                        ? 'active-row'
                        : 'text-white/70 hover:text-white hover:bg-white/[0.03]'}"
            >
              <span
                class="w-7 h-7 rounded border border-white/[0.10] flex-shrink-0"
                style="background: {t.background};"
              ></span>
              <span class="flex-1">{t.name}</span>
              <span
                class="w-2.5 h-2.5 rounded-full flex-shrink-0"
                style="background: {t.accent}; box-shadow: 0 0 8px {t.accent};"
              ></span>
            </button>
          {/each}
        </div>
      </div>
    </aside>
  </div>
{/if}
