<script>
  // Per-provider model config — the first-party twin of /ollamacloudconfig.
  // Lists every registry row for one provider (Anthropic or OpenAI) and lets
  // the user flip each active/inactive. The chat picker shows only active
  // rows, so this is where a freshly-synced model (e.g. a new Opus) opts in
  // — and where an old one gets retired.
  //
  // Refresh re-reads the provider's /v1/models via the backend sync endpoint.
  // Unlike Ollama Cloud, that read needs the provider API key in the API's
  // environment; a 503 comes back as a readable error if it's missing.
  import { onMount } from 'svelte'
  import { getProviderModels, setModelStatus, syncProviderModels } from '$lib/api.js'
  import { refreshModels } from '$lib/chat/modelsStore.js'
  import { apiKeys, refreshKeys } from '$lib/chat/keysStore.js'

  // provider: registry key ('anthropic'|'openai'); title: page heading;
  // keyEnv: the secret name this provider's models depend on.
  let { provider, title, keyEnv } = $props()

  // A provider's models are only meaningful once its key is in the broker
  // store: the chat picker can't reach the provider without it, and the
  // catalog sync needs it. So gate the whole list on key presence and react
  // live to add/rotate/delete on the Keys page (apiKeys is the shared store).
  const hasKey = $derived($apiKeys.some(k => k.name === keyEnv))

  let models  = $state([])
  let loading = $state(true)
  let syncing = $state(false)
  let status  = $state('')
  let error   = $state('')

  async function load() {
    try {
      models = await getProviderModels(provider)
      error = ''
    } catch (e) {
      error = e?.message ?? String(e)
    } finally {
      loading = false
    }
  }

  async function toggle(m) {
    const next = m.status === 'active' ? 'inactive' : 'active'
    // Optimistic flip; revert if the server rejects.
    const prior = m.status
    m.status = next
    models = [...models]
    try {
      await setModelStatus(m.model_id, next)
      // The chat sidebar's picker filters to active rows — refresh it so a
      // flip here lands there without a page reload.
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
      const r = await syncProviderModels(provider)
      status = `Catalog refreshed — ${r.inserted} new, ${r.refreshed} unchanged, ${r.deactivated} dropped.`
      await load()
      await refreshModels()
    } catch (e) {
      error = e?.message ?? String(e)
    } finally {
      syncing = false
    }
  }

  onMount(() => { refreshKeys(); load() })

  const active   = $derived(models.filter(m => m.status === 'active'))
  const inactive = $derived(models.filter(m => m.status !== 'active'))
</script>

<div class="px-6 pt-6 pb-12 max-w-[860px]">
  <div class="flex items-baseline justify-between mb-1">
    <h1 class="text-base font-medium text-white tracking-tight">{title}</h1>
    <button
      type="button"
      onclick={refresh}
      disabled={syncing || !hasKey}
      class="text-[11px] uppercase tracking-[0.15em] text-white/50 hover:text-white/90 transition disabled:opacity-40 disabled:cursor-wait"
    >
      {syncing ? 'Refreshing…' : 'Refresh catalog'}
    </button>
  </div>
  <p class="text-[12px] text-white/40 mb-6">
    Activate models to make them available in the chat picker.
    Refreshing the catalog requires <code class="text-white/60">{keyEnv}</code> in the broker's key store.
  </p>

  {#if status}
    <div class="mb-4 text-[12px] text-white/60 border border-white/[0.08] px-3 py-2 rounded">{status}</div>
  {/if}
  {#if error}
    <div class="mb-4 text-[12px] text-red-300/90 border border-red-300/20 px-3 py-2 rounded">{error}</div>
  {/if}

  {#if loading}
    <div class="text-white/40 text-sm">Loading…</div>
  {:else if !hasKey}
    <div class="text-[13px] text-white/55 border border-white/[0.08] rounded px-4 py-6 text-center">
      No <code class="text-white/75">{keyEnv}</code> in the key store yet.
      <a href="/keysconfig" class="text-white/85 underline underline-offset-2 hover:text-white">Add a key</a>
      to display available {title} models.
    </div>
  {:else if models.length === 0}
    <div class="text-white/40 text-sm">No {title} models in the registry. Click <em>Refresh catalog</em> to populate.</div>
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
                >{m.display_name ?? m.name}</a>
              {:else}
                <span class="flex-1 text-[12px] font-mono text-white/85 truncate">{m.display_name ?? m.name}</span>
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
        <ul class="divide-y divide-white/[0.06] border border-white/[0.08] rounded">
          {#each inactive as m (m.model_id)}
            <li class="flex items-center px-3 py-2.5">
              {#if m.source_url}
                <a
                  href={m.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  class="flex-1 text-[12px] font-mono text-white/60 hover:text-white/90 truncate hover:underline underline-offset-2"
                >{m.display_name ?? m.name}</a>
              {:else}
                <span class="flex-1 text-[12px] font-mono text-white/60 truncate">{m.display_name ?? m.name}</span>
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
      {/if}
    </section>
  {/if}
</div>
