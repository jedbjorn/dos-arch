<script>
  // Header dropdown for selecting which browser_chat shell the conversation
  // is bound to. Switching re-targets browser_chat on the API side (the
  // parent's onSwitch handles that + spinning up a fresh session).
  let { myShells = [], shellId = null, disabled = false, onSwitch } = $props()
</script>

{#if myShells.length}
  <select class="shell-select" value={shellId} {disabled}
    onchange={e => onSwitch(Number(e.target.value))}>
    {#each myShells as s}
      <option value={s.shell_id}>{s.display_name}</option>
    {/each}
  </select>
{:else}
  <span class="shell-name">No shell assigned</span>
{/if}

<style>
  .shell-name {
    flex: 1;
    font-size: 13px;
    font-weight: 700;
    color: var(--color-text);
    letter-spacing: 0.04em;
  }
  .shell-select {
    flex: 0 0 150px;
    background: transparent;
    border: none;
    color: var(--color-text);
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.04em;
    cursor: pointer;
    padding: 0;
    outline: none;
  }
  .shell-select option { background: var(--color-surface-2); color: var(--color-text); }
</style>
