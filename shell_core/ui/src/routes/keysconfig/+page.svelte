<script>
  // Keys — the secret-rotation surface (Phase 1, I3). Lists stored secret
  // metadata (name, last4, last-rotated) and lets the operator set/rotate/
  // delete. Values are write-only: typed into the field, sent to the API
  // (which relays to the broker, the secrets authority), and never read back
  // — the list only ever shows the last four characters.
  import { onMount } from 'svelte'
  import { getKeys, setKey, deleteKey, getShells, rotateShellKey } from '$lib/api.js'
  import { apiKeys } from '$lib/chat/keysStore.js'

  // The broker secrets injected on egress. This fixed set always renders as
  // rows — a row is "Add" when unset, "Rotate" once stored. Managing an
  // arbitrary secret would need backend wiring, so there is no free-text path.
  const KNOWN = ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'OLLAMA_CLOUD_API_KEY']

  // This page is the authority for the stored-keys list; it writes the shared
  // apiKeys store so provider config pages react to a set/rotate/delete here.
  let loading = $state(true)
  let status  = $state('')
  let error   = $state('')

  // The set/rotate form is a modal: modalKey holds the secret name being
  // edited (null = closed). The name is fixed by the row clicked — never typed.
  let modalKey = $state(null)
  let value    = $state('')
  let saving   = $state(false)

  // One row per KNOWN secret, merged with its stored metadata (if any).
  const rows = $derived(KNOWN.map((name) => ({
    name,
    stored: $apiKeys.find((k) => k.name === name) ?? null,
  })))

  // Shell substrate-API keys — distinct from the broker secrets above. These
  // live in the DB (api_key + api_key_hash); the dispatcher reads the plaintext
  // per turn to set each shell's Bearer. Long-lived; rotated here on demand.
  let shells     = $state([])
  let rotatingId = $state(null)

  async function load() {
    try {
      const [keys, shellRows] = await Promise.all([getKeys(), getShells()])
      apiKeys.set(keys)
      shells = shellRows
      error = ''
    } catch (e) {
      error = e?.message ?? String(e)
    } finally {
      loading = false
    }
  }

  async function rotateShell(s) {
    if (!confirm(`Rotate the API key for ${s.display_name}? Its current key stops working immediately; the dispatcher picks up the new one on its next turn.`)) return
    rotatingId = s.shell_id; status = ''; error = ''
    try {
      const r = await rotateShellKey(s.shell_id)
      status = `Rotated ${s.display_name} (${fmt(r.api_key_rotated_at)})`
      await load()
    } catch (e) {
      error = e?.message ?? String(e)
    } finally {
      rotatingId = null
    }
  }

  function openModal(n) {
    modalKey = n; value = ''; error = ''
  }

  function closeModal() {
    modalKey = null; value = ''
  }

  async function save() {
    if (!modalKey || !value) { error = 'value is required'; return }
    saving = true; status = ''; error = ''
    try {
      const m = await setKey(modalKey, value)
      status = `Saved ${m.name} (…${m.last_four})`
      closeModal()                     // drop the secret from component state at once
      await load()
    } catch (e) {
      error = e?.message ?? String(e)
    } finally {
      saving = false
    }
  }

  async function remove(k) {
    if (!confirm(`Delete ${k.name}? Egress that needs it will fail until it is set again.`)) return
    status = ''; error = ''
    try {
      await deleteKey(k.name)
      status = `Deleted ${k.name}`
      await load()
    } catch (e) {
      error = e?.message ?? String(e)
    }
  }

  const fmt = (iso) => { try { return new Date(iso).toLocaleString() } catch { return iso || '—' } }

  onMount(load)
</script>

<div class="px-6 pt-6 pb-12 max-w-[860px]">
  <h1 class="text-base font-medium text-white tracking-tight mb-1">API Keys</h1>
  <p class="text-[12px] text-white/40 mb-6">
    Secrets are sealed in the broker's encrypted store — set and rotated here, never displayed.
    The list shows only the last four characters and when each was last rotated.
  </p>

  {#if status}
    <div class="mb-4 text-[12px] text-white/60 border border-white/[0.08] px-3 py-2 rounded">{status}</div>
  {/if}
  {#if error}
    <div class="mb-4 text-[12px] text-red-300/90 border border-red-300/20 px-3 py-2 rounded">{error}</div>
  {/if}

  <!-- provider secrets — fixed rows: Add when unset, Rotate when stored -->
  <section>
    <div class="text-[10px] uppercase tracking-[0.2em] text-white/30 mb-3">
      Provider secrets
    </div>
    {#if loading}
      <div class="text-white/40 text-sm">Loading…</div>
    {:else}
      <ul class="divide-y divide-white/[0.06] border border-white/[0.08] rounded">
        {#each rows as { name, stored } (name)}
          <li class="flex items-center gap-3 px-3 py-2.5">
            <span class="flex-1 text-[12px] font-mono text-white/85 truncate">{name}</span>
            {#if stored}
              <span class="text-[11px] font-mono text-white/40">…{stored.last_four}</span>
              <span class="text-[11px] text-white/30 w-40 text-right truncate" title="last rotated">{fmt(stored.last_rotated_at)}</span>
              <button type="button" onclick={() => openModal(name)}
                class="text-[11px] text-white/50 hover:text-white/90 transition px-2 py-1">Rotate</button>
              <button type="button" onclick={() => remove(stored)}
                class="text-[11px] text-red-300/70 hover:text-red-300 transition px-2 py-1">Delete</button>
            {:else}
              <span class="text-[11px] font-mono text-white/25 italic">not set</span>
              <span class="text-[11px] text-white/30 w-40 text-right">—</span>
              <button type="button" onclick={() => openModal(name)}
                class="text-[11px] text-white/50 hover:text-white/90 transition px-2 py-1">Add</button>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <!-- shell substrate-API keys -->
  <section class="mt-8">
    <div class="text-[10px] uppercase tracking-[0.2em] text-white/30 mb-1">
      Shell keys ({shells.length})
    </div>
    <p class="text-[11px] text-white/30 mb-3">
      Each shell's substrate-API Bearer, stored in the DB and read by the dispatcher.
      Long-lived; rotating one invalidates that shell's current key at once.
    </p>
    {#if loading}
      <div class="text-white/40 text-sm">Loading…</div>
    {:else if shells.length === 0}
      <div class="text-[12px] text-white/30 italic">No shells.</div>
    {:else}
      <ul class="divide-y divide-white/[0.06] border border-white/[0.08] rounded">
        {#each shells as s (s.shell_id)}
          <li class="flex items-center gap-3 px-3 py-2.5">
            <span class="flex-1 text-[12px] font-mono text-white/85 truncate">{s.display_name}</span>
            <span class="text-[11px] font-mono {s.has_key ? 'text-white/40' : 'text-red-300/70'}">
              {s.has_key ? 'keyed' : 'no key'}
            </span>
            <span class="text-[11px] text-white/30 w-40 text-right truncate" title="key set / last rotated">{fmt(s.api_key_rotated_at)}</span>
            <button type="button" onclick={() => rotateShell(s)} disabled={rotatingId === s.shell_id}
              class="text-[11px] text-white/50 hover:text-white/90 transition px-2 py-1 disabled:opacity-40 disabled:cursor-not-allowed">
              {rotatingId === s.shell_id ? 'Rotating…' : 'Rotate'}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </section>
</div>

{#if modalKey}
  <!-- set / rotate modal -->
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
       role="presentation" onclick={closeModal}>
    <div class="w-[420px] max-w-[90vw] border border-white/[0.12] rounded bg-[#0d0d0d] p-5"
         role="dialog" aria-modal="true" tabindex="-1"
         onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
      <div class="text-[10px] uppercase tracking-[0.2em] text-white/30 mb-1">
        {$apiKeys.some((k) => k.name === modalKey) ? 'Rotate' : 'Add'}
      </div>
      <div class="text-[13px] font-mono text-white/85 mb-4">{modalKey}</div>
      <!-- svelte-ignore a11y_autofocus -->
      <input
        type="password" bind:value placeholder="value (write-only)" autocomplete="off" autofocus
        onkeydown={(e) => { if (e.key === 'Enter' && value && !saving) save(); if (e.key === 'Escape') closeModal() }}
        class="w-full mb-4 bg-transparent border border-white/[0.08] rounded px-3 py-2 text-[12px] font-mono text-white/85 placeholder:text-white/25 focus:border-white/30 focus:outline-none"
      />
      <div class="flex justify-end gap-2">
        <button type="button" onclick={closeModal}
          class="text-[11px] uppercase tracking-[0.15em] text-white/50 hover:text-white/80 px-3 py-1.5 transition">Cancel</button>
        <button type="button" onclick={save} disabled={saving || !value}
          class="text-[11px] uppercase tracking-[0.15em] text-white/70 hover:text-white border border-white/[0.12] rounded px-3 py-1.5 transition disabled:opacity-40 disabled:cursor-not-allowed">
          {saving ? 'Saving…' : 'Save'}</button>
      </div>
    </div>
  </div>
{/if}
