<script>
  // "Skills ▾" header button + popover. Lazy-loads the shell's skills on
  // first open. Hovered rows raise a tooltip with the full description
  // (600ms delay). Clicking a row with a slash command fires onCommand with
  // the command string — the parent decides what to do with it (typically:
  // prepend it into the draft and focus the input).
  import { onDestroy, tick } from 'svelte'
  import { getShellSkills } from '$lib/api.js'
  import { parseArgs, parseRequires } from '$lib/chat/skills.js'

  let { shellId = null, onCommand } = $props()

  let showSkills  = $state(false)
  let skills      = $state([])
  let popoverEl   = $state(null)
  let hoverTimer  = $state(null)
  let hoveredDesc = $state('')
  let hoveredTop  = $state(0)
  let hoveredLeft = $state(0)

  // Reset the cache when the shell changes so the next open re-fetches.
  $effect(() => { shellId; skills = []; showSkills = false })

  async function toggle() {
    showSkills = !showSkills
    if (!showSkills) { clearTimeout(hoverTimer); hoveredDesc = '' }
    if (showSkills && skills.length === 0 && shellId) {
      try { skills = await getShellSkills(shellId) } catch {}
    }
  }

  function onEnter(e, skill) {
    clearTimeout(hoverTimer)
    const rect = e.currentTarget.getBoundingClientRect()
    hoverTimer = setTimeout(() => {
      hoveredDesc = skill.description || ''
      hoveredTop  = rect.top
      hoveredLeft = rect.left
    }, 600)
  }

  function onLeave() {
    clearTimeout(hoverTimer)
    hoveredDesc = ''
  }

  async function pick(skill) {
    if (!skill.command) return
    showSkills = false
    clearTimeout(hoverTimer); hoveredDesc = ''
    await tick()
    onCommand?.(skill.command)
  }

  function onWindowClick(e) {
    if (!showSkills) return
    if (popoverEl && !popoverEl.contains(e.target)) showSkills = false
  }

  onDestroy(() => clearTimeout(hoverTimer))
</script>

<svelte:window onclick={onWindowClick} />

<div class="skills-wrap" bind:this={popoverEl}>
  <button class="skills-btn" class:active={showSkills}
    onclick={e => { e.stopPropagation(); toggle() }}>Skills ▾</button>

  {#if showSkills}
    <div class="skills-popover">
      {#if skills.length === 0}
        <div class="skills-empty">No skills assigned.</div>
      {:else}
        {#each skills as skill}
          <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
          <div class="skill-row" class:clickable={!!skill.command}
            onmouseenter={e => onEnter(e, skill)}
            onmouseleave={onLeave}
            onclick={skill.command ? () => pick(skill) : null}>
            <span class="skill-name">{skill.name}</span>
            <span class="skill-args">{parseArgs(skill.description) || skill.command || ''}</span>
            {#if parseRequires(skill.description)}
              <span class="skill-hint">{parseRequires(skill.description)}</span>
            {/if}
          </div>
        {/each}
      {/if}
    </div>
    {#if hoveredDesc}
      <div class="skill-tip" style="top:{hoveredTop}px;left:{hoveredLeft - 8}px">{hoveredDesc}</div>
    {/if}
  {/if}
</div>

<style>
  /* The wrap stays inline so the button sits in the header flow; the popover
     anchors absolutely off the wrap and the surrounding `.chat-header`. */
  .skills-wrap { margin-left: auto; position: relative; }

  .skills-btn {
    background: none;
    border: 1px solid var(--color-border);
    border-radius: 4px;
    color: var(--color-text-dim);
    font-family: var(--font-mono);
    font-size: 10px;
    cursor: pointer;
    padding: 2px 7px;
    letter-spacing: 0.04em;
  }
  .skills-btn:hover, .skills-btn.active { color: var(--color-accent); border-color: var(--color-accent); }

  .skills-popover {
    position: absolute;
    top: 100%; right: 0;
    width: 250px;
    background: var(--color-surface-2);
    border: 1px solid var(--color-border);
    border-top: none;
    border-radius: 0 0 8px 8px;
    z-index: 10;
    max-height: 420px;
    overflow-y: auto;
    padding: 6px 0;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  }
  .skill-row { display: flex; flex-direction: column; padding: 8px 14px; gap: 3px; cursor: default; }
  .skill-row.clickable { cursor: pointer; }
  .skill-row:hover { background: var(--color-surface-3); }
  .skill-name { font-family: var(--font-mono); font-size: 12px; font-weight: 600; color: #fff; word-break: break-word; }
  .skill-args { font-family: var(--font-mono); font-size: 10px; color: var(--color-text-muted); word-break: break-word; }
  .skill-hint { font-family: var(--font-mono); font-size: 10px; font-style: italic; color: var(--color-amber); word-break: break-word; margin-top: 2px; }
  .skills-empty { padding: 10px 14px; font-family: var(--font-mono); font-size: 11px; color: var(--color-text-dim); }

  .skill-tip {
    position: fixed;
    transform: translateX(-100%);
    margin-left: -8px;
    max-width: 320px;
    padding: 10px 12px;
    background: var(--color-surface-2);
    color: var(--color-text);
    border: 1px solid var(--color-border);
    border-radius: 6px;
    font-size: 11px;
    line-height: 1.45;
    z-index: 20;
    box-shadow: 0 4px 20px rgba(0,0,0,0.6);
    pointer-events: none;
  }
</style>
