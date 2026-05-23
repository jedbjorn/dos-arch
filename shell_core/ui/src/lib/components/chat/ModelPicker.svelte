<script>
  // Available-models column — providers grouped, click a row to switch the
  // current conversation's pinned model. Parent's onChange takes the
  // selected model_id as a string ('' = none pinned).
  import { PROVIDERS, modelsByProvider, modelLabel } from '$lib/chat/models.js'

  let { models = [], selectedModel = '', onChange } = $props()
  const grouped = $derived(modelsByProvider(models))
</script>

<div class="models-col">
  <div class="col-title">Available Models</div>
  <div class="models-list">
    {#each PROVIDERS as p}
      <div class="provider-group">
        <div class="provider-head">{p.label}</div>
        {#each grouped[p.key] ?? [] as m}
          <button class="model-row" class:active={String(m.model_id) === selectedModel}
            onclick={() => onChange(String(m.model_id))}>{modelLabel(m)}</button>
        {/each}
        {#if !(grouped[p.key] ?? []).length}
          <div class="model-none">(none yet)</div>
        {/if}
      </div>
    {/each}
  </div>
</div>

<style>
  .models-col {
    width: 140px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--color-border);
    background: var(--color-surface-2);
  }
  .col-title {
    height: 52px;            /* aligns with the chat-header divider */
    display: flex;
    align-items: center;
    padding: 0 12px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.04em;
    color: var(--color-text);
    border-bottom: 1px solid var(--color-border);
  }
  .models-list { flex: 1; overflow-y: auto; padding: 6px 0; }
  .provider-group { margin-bottom: 8px; }
  .provider-head {
    padding: 6px 12px 3px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--color-accent);
  }
  .model-row {
    display: block;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    border-left: 2px solid transparent;
    color: var(--color-text-dim);
    font-family: var(--font-mono);
    font-size: 11px;
    cursor: pointer;
    padding: 4px 12px;
    line-height: 1.3;
  }
  .model-row:hover { color: var(--color-text); background: var(--color-surface-3); }
  .model-row.active {
    color: var(--color-text);
    border-left-color: var(--color-accent);
    background: color-mix(in srgb, var(--color-accent) 14%, transparent);
  }
  .model-none {
    padding: 3px 12px;
    font-size: 10px;
    font-style: italic;
    color: var(--color-text-muted);
  }
</style>
