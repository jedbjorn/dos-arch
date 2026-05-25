<script>
  // "Skills" header button + popover. Lazy-loads the shell's skills on
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

<div class="ml-auto relative" bind:this={popoverEl}>
  <button
    onclick={e => { e.stopPropagation(); toggle() }}
    class="px-3 py-1.5 rounded-full text-xs border transition
           {showSkills
              ? 'text-white border-white/20 bg-white/[0.04]'
              : 'text-white/60 hover:text-white/90 border-white/10 hover:border-white/20'}"
  >
    Skills
  </button>

  {#if showSkills}
    <!-- Popover: solid medium-grey card hanging off the right edge of the header. -->
    <div
      class="absolute top-full right-0 mt-2 w-max max-w-[80vw] max-h-[420px] overflow-y-auto rounded-2xl border py-2 z-10"
      style="background: var(--menu-bg);
             border-color: var(--menu-border);
             box-shadow: var(--menu-shadow);"
    >
      {#if skills.length === 0}
        <div class="px-4 py-2.5 text-[11px] text-white/40">No skills assigned.</div>
      {:else}
        {#each skills as skill}
          <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
          <div
            role="button"
            tabindex={skill.command ? 0 : -1}
            class="flex flex-col gap-1 px-4 py-2 transition
                   {skill.command ? 'cursor-pointer hover:bg-white/[0.06]' : 'cursor-default'}"
            onmouseenter={e => onEnter(e, skill)}
            onmouseleave={onLeave}
            onclick={skill.command ? () => pick(skill) : null}
          >
            <span class="text-[12px] font-mono font-semibold text-white break-words">{skill.name}</span>
            <span class="text-[10px] font-mono text-white/40 break-words">
              {parseArgs(skill.description) || skill.command || ''}
            </span>
            {#if parseRequires(skill.description)}
              <span class="text-[10px] italic text-amber break-words">{parseRequires(skill.description)}</span>
            {/if}
          </div>
        {/each}
      {/if}
    </div>
    {#if hoveredDesc}
      <div
        class="fixed -translate-x-full max-w-[320px] px-3 py-2.5 rounded-lg border border-white/[0.10] text-[11px] text-white/90 leading-relaxed z-20 pointer-events-none"
        style="top: {hoveredTop}px;
               left: {hoveredLeft - 8}px;
               margin-left: -8px;
               background: rgba(20, 20, 30, 0.96);
               box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);"
      >{hoveredDesc}</div>
    {/if}
  {/if}
</div>
