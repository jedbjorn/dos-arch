<script>
  // Header dropdown for selecting which browser_chat shell the conversation
  // is bound to. Switching re-targets browser_chat on the API side (the
  // parent's onSwitch handles that + spinning up a fresh session).
  import GlassDropdown from '../GlassDropdown.svelte'

  let { myShells = [], shellId = null, disabled = false, onSwitch } = $props()

  // Map shells → dropdown items: name + (shared) suffix.
  const items = $derived(myShells.map(s => ({
    value:  s.shell_id,
    label:  s.display_name,
    suffix: s.is_shared ? '(shared)' : null,
  })))
</script>

{#if myShells.length}
  <GlassDropdown
    value={shellId}
    {items}
    {disabled}
    onChange={v => onSwitch(Number(v))}
  />
{:else}
  <span class="text-sm text-white/60">No shell assigned</span>
{/if}
