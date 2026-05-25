<script>
  // Ollama Cloud config — list every cloud row from the registry and let the
  // user flip each one active/inactive. The plain /models picker shows only
  // active rows, so this is the surface where the catalog opts in.
  //
  // Refresh button re-hits /api/tags via the backend sync endpoint; counts
  // come back in the response and surface in a transient status line.
  import { onMount } from 'svelte'
  import { getCloudModels, setModelStatus, syncCloudModels } from '$lib/api.js'
  import { refreshModels } from '$lib/chat/modelsStore.js'

  // Family resolver — Ollama Cloud's /api/tags returns empty `family`/`families`
  // fields for every cloud entry, so we infer the maker from the name prefix
  // for the group headers below. Purely presentational; if a new family lands
  // upstream and falls into 'Other', add a rule here.
  const FAMILY_RULES = [
    [/^(mistral|ministral|mixtral|devstral|magistral)/i, 'Mistral'],
    [/^(gemma|gemini)/i,        'Google'],
    [/^deepseek/i,              'DeepSeek'],
    [/^qwen/i,                  'Alibaba'],
    [/^llama/i,                 'Meta'],
    [/^glm/i,                   'Z.ai'],
    [/^kimi/i,                  'Moonshot'],
    [/^gpt-oss/i,               'OpenAI'],
    [/^nemotron/i,              'NVIDIA'],
    [/^cogito/i,                'DeepCogito'],
    [/^minimax/i,               'MiniMax'],
  ]
  function familyOf(name) {
    for (const [re, label] of FAMILY_RULES) if (re.test(name)) return label
    return 'Other'
  }

  // Group an array of model rows into [{ family, rows }, …] sorted by group
  // size descending so the densest families (Qwen, DeepSeek, …) lead. 'Other'
  // is always pushed to the bottom regardless of size so unknown rows don't
  // crowd the top.
  function groupByFamily(rows) {
    const buckets = new Map()
    for (const r of rows) {
      const f = familyOf(r.name)
      if (!buckets.has(f)) buckets.set(f, [])
      buckets.get(f).push(r)
    }
    return [...buckets.entries()]
      .map(([family, rows]) => ({ family, rows }))
      .sort((a, b) => {
        if (a.family === 'Other') return 1
        if (b.family === 'Other') return -1
        return b.rows.length - a.rows.length
      })
  }

  let models  = $state([])
  let loading = $state(true)
  let syncing = $state(false)
  let status  = $state('')
  let error   = $state('')

  async function load() {
    try {
      models = await getCloudModels()
      error = ''
    } catch (e) {
      error = e?.message ?? String(e)
    } finally {
      loading = false
    }
  }

  async function toggle(m) {
    const next = m.status === 'active' ? 'inactive' : 'active'
    // Optimistic flip so the UI feels live; revert if the server rejects.
    const prior = m.status
    m.status = next
    models = [...models]
    try {
      await setModelStatus(m.model_id, next)
      // Notify the persistent chat sidebar — its model picker filters to
      // active rows, so flipping status here must reach there without a
      // page reload.
      await refreshModels()
    } catch (e) {
      m.status = prior
      models = [...models]
      error = `${m.name}: ${e?.message ?? e}`
    }
  }

  async function refresh() {
    syncing = true; status = ''; error = ''
    try {
      const r = await syncCloudModels()
      status = `Catalog refreshed — ${r.inserted} new, ${r.refreshed} unchanged, ${r.deactivated} dropped.`
      await load()
      await refreshModels()
    } catch (e) {
      error = e?.message ?? String(e)
    } finally {
      syncing = false
    }
  }

  onMount(load)

  const active         = $derived(models.filter(m => m.status === 'active'))
  const inactive       = $derived(models.filter(m => m.status !== 'active'))
  const inactiveGroups = $derived(groupByFamily(inactive))
</script>

<div class="px-6 pt-6 pb-12 max-w-[860px]">
  <div class="flex items-baseline justify-between mb-1">
    <h1 class="text-base font-medium text-white tracking-tight">Ollama Cloud</h1>
    <button
      type="button"
      onclick={refresh}
      disabled={syncing}
      class="text-[11px] uppercase tracking-[0.15em] text-white/50 hover:text-white/90 transition disabled:opacity-40 disabled:cursor-wait"
    >
      {syncing ? 'Refreshing…' : 'Refresh catalog'}
    </button>
  </div>
  <p class="text-[12px] text-white/40 mb-6">
    Activate cloud models to make them available in the chat picker.
    Requires <code class="text-white/60">OLLAMA_CLOUD_API_KEY</code> in the dispatcher's environment.
  </p>

  {#if status}
    <div class="mb-4 text-[12px] text-white/60 border border-white/[0.08] px-3 py-2 rounded">{status}</div>
  {/if}
  {#if error}
    <div class="mb-4 text-[12px] text-red-300/90 border border-red-300/20 px-3 py-2 rounded">{error}</div>
  {/if}

  {#if loading}
    <div class="text-white/40 text-sm">Loading…</div>
  {:else if models.length === 0}
    <div class="text-white/40 text-sm">No cloud models in the registry. Click <em>Refresh catalog</em> to populate.</div>
  {:else}
    <section class="mb-8">
      <div class="text-[10px] uppercase tracking-[0.2em] text-white/30 mb-3">
        Active ({active.length})
      </div>
      {#if active.length === 0}
        <div class="text-[12px] text-white/30 italic">None activated yet.</div>
      {:else}
        <ul class="divide-y divide-white/[0.06] border border-white/[0.08] rounded">
          {#each active as m (m.model_id)}
            <li class="flex items-center px-3 py-2.5">
              {#if m.source_url}
                <a
                  href={m.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  class="flex-1 text-[12px] font-mono text-white/85 hover:text-white truncate hover:underline underline-offset-2"
                >{m.name}</a>
              {:else}
                <span class="flex-1 text-[12px] font-mono text-white/85 truncate">{m.name}</span>
              {/if}
              <button
                type="button"
                onclick={() => toggle(m)}
                class="text-[11px] text-white/50 hover:text-white/90 transition px-2 py-1"
                aria-label="Deactivate {m.name}"
              >Deactivate</button>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <section>
      <div class="text-[10px] uppercase tracking-[0.2em] text-white/30 mb-3">
        Available ({inactive.length})
      </div>
      {#if inactive.length === 0}
        <div class="text-[12px] text-white/30 italic">Everything is active.</div>
      {:else}
        {#each inactiveGroups as g (g.family)}
          <div class="mb-3 last:mb-0">
            <div class="text-[10px] uppercase tracking-[0.15em] text-white/40 mb-1.5">
              {g.family} <span class="text-white/25">({g.rows.length})</span>
            </div>
            <ul class="divide-y divide-white/[0.06] border border-white/[0.08] rounded">
              {#each g.rows as m (m.model_id)}
                <li class="flex items-center px-3 py-2.5">
                  {#if m.source_url}
                    <a
                      href={m.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      class="flex-1 text-[12px] font-mono text-white/60 hover:text-white/90 truncate hover:underline underline-offset-2"
                    >{m.name}</a>
                  {:else}
                    <span class="flex-1 text-[12px] font-mono text-white/60 truncate">{m.name}</span>
                  {/if}
                  <button
                    type="button"
                    onclick={() => toggle(m)}
                    class="text-[11px] text-white/50 hover:text-white/90 transition px-2 py-1"
                    aria-label="Activate {m.name}"
                  >Activate</button>
                </li>
              {/each}
            </ul>
          </div>
        {/each}
      {/if}
    </section>
  {/if}
</div>
