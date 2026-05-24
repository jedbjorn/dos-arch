<script>
  // Renders Markdown text to sanitized HTML via marked + DOMPurify.
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
  /* Markdown surfaces tuned for the spatial-glass canvas — code blocks
     read as small glass cards, blockquotes use hairlines, headings step
     down through the white-alpha ramp. */
  .md { overflow-wrap: break-word; color: rgba(255, 255, 255, 0.90); }
  .md :global(h1), .md :global(h2), .md :global(h3), .md :global(h4) {
    font-size: 0.8rem; font-weight: 600; letter-spacing: 0.15em;
    text-transform: uppercase; color: rgba(255, 255, 255, 0.40); margin: 0.9em 0 0.3em;
  }
  .md :global(h1:first-child), .md :global(h2:first-child), .md :global(h3:first-child) { margin-top: 0; }
  .md :global(p) { margin: 0.4em 0; }
  .md :global(p:first-child) { margin-top: 0; }
  .md :global(p:last-child)  { margin-bottom: 0; }
  .md :global(ul), .md :global(ol) { margin: 0.4em 0; padding-left: 1.3em; }
  .md :global(li) { margin: 0.15em 0; }
  .md :global(a)  { color: var(--color-accent); text-decoration: underline; }
  .md :global(strong) { font-weight: 600; color: white; }
  .md :global(em) { font-style: italic; }

  .md :global(code) {
    background: var(--menu-bg);
    border: 1px solid var(--menu-border);
    padding: 0.05em 0.35em;
    border-radius: 4px;
    font-family: var(--font-mono);
    font-size: 0.93em;
    overflow-wrap: anywhere;
  }
  .md :global(pre) {
    background: var(--menu-bg);
    border: 1px solid var(--menu-border);
    padding: 0.7em 0.9em;
    border-radius: 10px;
    font-family: var(--font-mono);
    font-size: 0.9em;
    margin: 0.6em 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .md :global(pre code) { background: transparent; border: 0; padding: 0; }

  .md :global(blockquote) {
    border-left: 2px solid rgba(255, 255, 255, 0.15);
    margin: 0.6em 0;
    padding: 0.1em 0.9em;
    color: rgba(255, 255, 255, 0.60);
  }
  .md :global(hr) {
    border: 0;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    margin: 0.9em 0;
  }

  /* Tables — render as proper grids, with column A (term) never breaking
     mid-word and the meaning column driving the wrap. `display: block` +
     `overflow-x: auto` lets a too-wide table scroll inside its section
     instead of clipping the panel. */
  .md :global(table) {
    display: block;
    width: 100%;
    max-width: 100%;
    overflow-x: auto;
    border-collapse: collapse;
    margin: 0.6em 0;
    font-size: 0.93em;
  }
  .md :global(thead) {
    border-bottom: 1px solid rgba(255, 255, 255, 0.15);
  }
  .md :global(th), .md :global(td) {
    padding: 0.4em 0.7em;
    text-align: left;
    vertical-align: top;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    word-break: normal;
    overflow-wrap: break-word;
  }
  .md :global(th) {
    font-weight: 600;
    text-transform: uppercase;
    font-size: 0.78em;
    letter-spacing: 0.06em;
    color: rgba(255, 255, 255, 0.55);
  }
  .md :global(tr:last-child td) { border-bottom: 0; }
  /* Column A — strict word-boundary breaks, never mid-word. Wraps between
     words for multi-word terms ("tool / tooling"); a single long token like
     `current_state` holds the line and the row's wrap is driven by col B. */
  .md :global(td:first-child), .md :global(th:first-child) {
    word-break: keep-all;
    overflow-wrap: normal;
    white-space: normal;
    color: white;
    font-family: var(--font-mono);
    font-size: 0.92em;
    padding-right: 1em;
  }
</style>
