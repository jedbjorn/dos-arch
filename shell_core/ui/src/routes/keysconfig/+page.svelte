<script>
  // Keys — the secret-rotation surface (Phase 1, I3). Lists stored secret
  // metadata (name, last4, last-rotated) and lets the operator set/rotate/
  // delete. Values are write-only: typed into the field, sent to the API
  // (which relays to the broker, the secrets authority), and never read back
  // — the list only ever shows the last four characters.
  import { onMount } from 'svelte'
  import { getKeys, setKey, deleteKey, getShells, rotateShellKey } from '$lib/api.js'
  import { apiKeys } from '$lib/chat/keysStore.js'

  // The secrets the broker injects on egress — offered as quick picks; a custom
  // name is allowed for anything else stored.
  const KNOWN = ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'OLLAMA_CLOUD_API_KEY', 'GITHUB_TOKEN']

  // This page is the authority for the stored-keys list; it writes the shared
  // apiKeys store so provider config pages react to a set/rotate/delete here.
  let loading = $state(true)
  let status  = $state('')
  let error   = $state('')

  let name   = $state('ANTHROPIC_API_KEY')
  let value  = $state('')
  let saving = $state(false)

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

  async function save() {
    if (!name || !value) { error = 'name and value are both required'; return }
    saving = true; status = ''; error = ''
    try {
      const m = await setKey(name.trim(), value)
      status = `Saved ${m.name} (…${m.last_four})`
      value = ''                       // drop the secret from component state at once
      await load()
    } catch (e) {
      error = e?.message ?? String(e)
    } finally {
      saving = false
    }
  }

  function rotate(n) {
    name = n; value = ''; status = `Enter a new value for ${n}, then Save to rotate.`; error = ''
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

  <!-- set / rotate -->
  <section class="mb-8 border border-white/[0.08] rounded p-4">
    <div class="text-[10px] uppercase tracking-[0.2em] text-white/30 mb-3">Set / rotate</div>
    <div class="flex flex-wrap gap-2 mb-3">
      {#each KNOWN as k}
        <button type="button" onclick={() => name = k}
          class="text-[11px] font-mono px-2 py-1 rounded border transition
                 {name === k ? 'border-white/30 text-white/90' : 'border-white/[0.08] text-white/50 hover:text-white/80'}">
          {k}
        </button>
      {/each}
    </div>
    <input
      type="text" bind:value={name} placeholder="SECRET_NAME"
      class="w-full mb-2 bg-transparent border border-white/[0.08] rounded px-3 py-2 text-[12px] font-mono text-white/85 placeholder:text-white/25 focus:border-white/30 focus:outline-none"
    />
    <input
      type="password" bind:value={value} placeholder="value (write-only)" autocomplete="off"
      class="w-full mb-3 bg-transparent border border-white/[0.08] rounded px-3 py-2 text-[12px] font-mono text-white/85 placeholder:text-white/25 focus:border-white/30 focus:outline-none"
    />
    <button
      type="button" onclick={save} disabled={saving || !name || !value}
      class="text-[11px] uppercase tracking-[0.15em] text-white/70 hover:text-white border border-white/[0.12] rounded px-3 py-1.5 transition disabled:opacity-40 disabled:cursor-not-allowed"
    >{saving ? 'Saving…' : 'Save'}</button>
  </section>

  <!-- stored -->
  <section>
    <div class="text-[10px] uppercase tracking-[0.2em] text-white/30 mb-3">
      Stored ({$apiKeys.length})
    </div>
    {#if loading}
      <div class="text-white/40 text-sm">Loading…</div>
    {:else if $apiKeys.length === 0}
      <div class="text-[12px] text-white/30 italic">No secrets stored yet.</div>
    {:else}
      <ul class="divide-y divide-white/[0.06] border border-white/[0.08] rounded">
        {#each $apiKeys as k (k.name)}
          <li class="flex items-center gap-3 px-3 py-2.5">
            <span class="flex-1 text-[12px] font-mono text-white/85 truncate">{k.name}</span>
            <span class="text-[11px] font-mono text-white/40">…{k.last_four}</span>
            <span class="text-[11px] text-white/30 w-40 text-right truncate" title="last rotated">{fmt(k.last_rotated_at)}</span>
            <button type="button" onclick={() => rotate(k.name)}
              class="text-[11px] text-white/50 hover:text-white/90 transition px-2 py-1">Rotate</button>
            <button type="button" onclick={() => remove(k)}
              class="text-[11px] text-red-300/70 hover:text-red-300 transition px-2 py-1">Delete</button>
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
