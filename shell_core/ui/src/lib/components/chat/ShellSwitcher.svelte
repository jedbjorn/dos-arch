<script>
  // Header dropdown for selecting which browser_chat shell the conversation
  // is bound to. Switching re-targets browser_chat on the API side (the
  // parent's onSwitch handles that + spinning up a fresh session).
  let { myShells = [], shellId = null, disabled = false, onSwitch } = $props()

  const activeShell = $derived(myShells.find(s => s.shell_id === shellId))
</script>

{#if myShells.length}
  <!-- Avatar orb + native select styled to look like a chevron-pill.
       Native <select> preserved for free dropdown UX; the visible chrome
       around it is what changes. -->
  <div class="relative flex items-center gap-3 group">
    <div
      class="w-7 h-7 rounded-full shrink-0"
      style="background: var(--orb-grad); box-shadow: 0 0 12px var(--orb-glow);"
    ></div>
    <div class="flex flex-col items-start leading-tight min-w-0">
      <div class="text-sm text-white font-medium truncate">
        {activeShell?.display_name ?? 'Shell'}
      </div>
      {#if activeShell?.shortname}
        <div class="text-[10px] text-white/40 leading-tight mt-0.5 truncate font-mono">
          {activeShell.shortname}
        </div>
      {/if}
    </div>
    <svg
      class="text-white/40 group-hover:text-white/80 ml-1 transition shrink-0"
      width="10" height="14" viewBox="0 0 10 14" fill="none" stroke="currentColor"
      stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"
    >
      <polyline points="2.5,5 5,2.5 7.5,5" />
      <polyline points="2.5,9 5,11.5 7.5,9" />
    </svg>
    <select
      class="absolute inset-0 opacity-0 cursor-pointer"
      value={shellId}
      {disabled}
      onchange={e => onSwitch(Number(e.target.value))}
      aria-label="Switch shell"
    >
      {#each myShells as s}
        <option value={s.shell_id}>{s.display_name}</option>
      {/each}
    </select>
  </div>
{:else}
  <span class="text-sm text-white/60">No shell assigned</span>
{/if}
