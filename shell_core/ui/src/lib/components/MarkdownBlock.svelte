<script>
  import { marked } from 'marked'
  import DOMPurify from 'dompurify'

  let { text = '' } = $props()

  marked.setOptions({ gfm: true, breaks: true })

  const html = $derived(
    text ? DOMPurify.sanitize(marked.parse(String(text)), { USE_PROFILES: { html: true } }) : ''
  )
</script>

{#if html}
  <div class="md">{@html html}</div>
{/if}

<style>
  .md { word-break: break-word; }
  .md :global(h1), .md :global(h2), .md :global(h3), .md :global(h4) {
    font-size: 0.8rem; font-weight: 600; letter-spacing: 0.04em;
    text-transform: uppercase; color: var(--color-text-dim); margin: 0.9em 0 0.3em;
  }
  .md :global(h1:first-child), .md :global(h2:first-child), .md :global(h3:first-child) { margin-top: 0; }
  .md :global(p) { margin: 0.4em 0; }
  .md :global(p:first-child) { margin-top: 0; }
  .md :global(p:last-child)  { margin-bottom: 0; }
  .md :global(ul), .md :global(ol) { margin: 0.4em 0; padding-left: 1.3em; }
  .md :global(li) { margin: 0.15em 0; }
  .md :global(a)  { color: var(--color-accent); text-decoration: underline; }
  .md :global(code) { background: var(--color-surface-3); padding: 0.05em 0.3em; border-radius: 3px; font-size: 0.85em; overflow-wrap: anywhere; }
  .md :global(pre)  { background: var(--color-surface-3); padding: 0.6em 0.8em; border-radius: 4px; font-size: 0.82em; margin: 0.5em 0; white-space: pre-wrap; overflow-wrap: anywhere; }
  .md :global(pre code) { background: transparent; padding: 0; }
  .md :global(blockquote) { border-left: 3px solid var(--color-border); margin: 0.5em 0; padding: 0.1em 0.8em; color: var(--color-text-dim); }
  .md :global(hr) { border: 0; border-top: 1px solid var(--color-border); margin: 0.8em 0; }
  .md :global(strong) { font-weight: 600; }
  .md :global(em) { font-style: italic; }
</style>
