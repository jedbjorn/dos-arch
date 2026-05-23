<script>
  // Shells viewer — inspect an assigned shell's rendered boot prompt and
  // toggle which skills are assigned to it. Sticky identity sub-header
  // below the TopBar; glass-panel sections for the prompt accordions and
  // skill viewer. (redline: shared/redlines/Shells Tab.png)
  import { onMount } from 'svelte'
  import {
    getMyShells, getShell, getShellPromptSections,
    getAvailableSkills, getShellSkills, getSkill,
    addShellSkill, removeShellSkill,
  } from '$lib/api.js'
  import MarkdownBlock from '$lib/components/MarkdownBlock.svelte'
  import GlassDropdown from '$lib/components/GlassDropdown.svelte'

  let myShells   = $state([])
  let shellId    = $state(null)
  let shell      = $state(null)
  let sections   = $state([])
  let openLabels = $state(new Set())          // accordions, all collapsed by default

  let allSkills  = $state([])                 // every assignable skill (admin list)
  let assignedIds = $state(new Set())         // skill_ids currently assigned to shellId
  let activeSkillId = $state(null)
  let activeSkill = $state(null)              // {skill_id, name, description, content}
  let skillsOpen  = $state(false)
  let skillBtnRef = $state(null)

  let loading    = $state(false)
  let error      = $state('')

  async function loadShellData(id) {
    if (!id) return
    loading = true
    error = ''
    openLabels = new Set()
    activeSkillId = null
    activeSkill = null
    try {
      const [sh, secs, available, assigned] = await Promise.all([
        getShell(id),
        getShellPromptSections(id),
        getAvailableSkills(),
        getShellSkills(id),
      ])
      shell = sh
      sections = secs
      allSkills = available
      assignedIds = new Set(assigned.map(s => s.skill_id))
      // Default selection: first assigned skill, else first overall.
      const firstAssigned = available.find(s => assignedIds.has(s.skill_id))
      const first = firstAssigned ?? available[0] ?? null
      if (first) selectSkill(first.skill_id)
    } catch (e) {
      error = String(e.message ?? e)
    } finally {
      loading = false
    }
  }

  async function selectSkill(skill_id) {
    activeSkillId = skill_id
    try {
      activeSkill = await getSkill(skill_id)
    } catch (e) {
      activeSkill = null
      error = String(e.message ?? e)
    }
  }

  async function toggleAssigned(skill_id) {
    if (!shellId) return
    const next = new Set(assignedIds)
    try {
      if (next.has(skill_id)) {
        await removeShellSkill(shellId, skill_id)
        next.delete(skill_id)
      } else {
        await addShellSkill(shellId, skill_id)
        next.add(skill_id)
      }
      assignedIds = next
      // Re-render the prompt — SKILLS AVAILABLE section reflects assignment.
      sections = await getShellPromptSections(shellId)
    } catch (e) {
      error = String(e.message ?? e)
    }
  }

  function toggle(label) {
    const next = new Set(openLabels)
    next.has(label) ? next.delete(label) : next.add(label)
    openLabels = next
  }

  function onDocClick(e) {
    if (!skillsOpen) return
    if (skillBtnRef && skillBtnRef.contains(e.target)) return
    skillsOpen = false
  }

  onMount(async () => {
    document.addEventListener('mousedown', onDocClick)
    try {
      myShells = await getMyShells()
      shellId = myShells[0]?.shell_id ?? null
    } catch (e) {
      error = String(e.message ?? e)
    }
    return () => document.removeEventListener('mousedown', onDocClick)
  })

  $effect(() => {
    if (shellId) loadShellData(shellId)
  })

  const shellItems = $derived(myShells.map(s => ({
    value:   s.shell_id,
    label:   s.display_name,
    caption: s.shortname ?? null,
    suffix:  s.is_shared ? '(shared)' : null,
  })))
</script>

<!-- Sticky identity sub-header — sits below the TopBar (h-[52px]).
     Glass backdrop so content scrolls cleanly under it. -->
<header
  class="sticky top-[52px] z-20 px-6 py-4 flex flex-col gap-1 border-b border-white/[0.08]"
  style="background: rgba(255, 255, 255, 0.02);
         backdrop-filter: blur(24px);
         -webkit-backdrop-filter: blur(24px);"
>
  {#if myShells.length}
    <GlassDropdown
      value={shellId}
      items={shellItems}
      onChange={v => shellId = Number(v)}
    />
    {#if shell?.role}
      <div class="flex items-baseline gap-2 text-sm">
        <span class="text-[10px] uppercase tracking-[0.15em] text-white/30">Role</span>
        <span class="text-white/80">{shell.role}</span>
      </div>
    {/if}
  {/if}
</header>

<div class="px-6 pt-5 pb-10 flex flex-col gap-5">
  {#if error}
    <div class="text-red text-sm">{error}</div>
  {/if}

  <!-- Harness Prompt — single glass panel containing all accordion rows. -->
  <section class="flex flex-col gap-2">
    <h2 class="text-[10px] uppercase tracking-[0.15em] text-white/40 px-1">Harness Prompt</h2>
    <div
      class="rounded-2xl border border-white/[0.08] overflow-hidden"
      style="background: var(--glass-bg);
             backdrop-filter: blur(var(--glass-blur));
             -webkit-backdrop-filter: blur(var(--glass-blur));"
    >
      {#if loading && !sections.length}
        <div class="text-white/40 text-xs px-4 py-3">Loading…</div>
      {/if}
      {#each sections as sec, i}
        {@const open = openLabels.has(sec.label)}
        <div class={i > 0 ? 'border-t border-white/[0.06]' : ''}>
          <button
            type="button"
            onclick={() => toggle(sec.label)}
            class="w-full flex items-center gap-2 px-4 py-2.5 text-left text-[12px] font-mono font-semibold tracking-wider text-white/90 hover:bg-white/[0.03] transition"
          >
            <span class="text-white/40 w-3 text-xs">{open ? '▾' : '▸'}</span>
            <span class="uppercase">{sec.label}</span>
          </button>
          {#if open}
            <div class="px-5 pb-4 pt-3 border-t border-white/[0.06] text-[12px]">
              <MarkdownBlock text={sec.body} />
            </div>
          {/if}
        </div>
      {/each}
    </div>
  </section>

  <!-- Skill Viewer — header row + glass-panel body. -->
  <section class="flex flex-col gap-2">
    <div class="flex items-center gap-3 px-1">
      <h2 class="text-[10px] uppercase tracking-[0.15em] text-white/40 shrink-0">Skill Viewer</h2>
      <div class="relative ml-auto" bind:this={skillBtnRef}>
        <button
          type="button"
          onclick={() => skillsOpen = !skillsOpen}
          class="flex items-center gap-2 min-w-[18rem] px-3 py-1.5 rounded-full border text-xs transition
                 {skillsOpen
                    ? 'text-white border-white/20 bg-white/[0.04]'
                    : 'text-white/70 hover:text-white border-white/[0.10] hover:border-white/20'}"
        >
          <span class="flex-1 text-left font-mono truncate">
            {activeSkill?.name ?? (allSkills.length ? 'Select a skill' : '—')}
          </span>
          <svg
            class="text-white/40 shrink-0"
            width="10" height="14" viewBox="0 0 10 14" fill="none" stroke="currentColor"
            stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"
          >
            <polyline points="2.5,5 5,2.5 7.5,5" />
            <polyline points="2.5,9 5,11.5 7.5,9" />
          </svg>
        </button>
        {#if skillsOpen && allSkills.length}
          <!-- Solid medium-grey popover — same treatment as SkillsPopover + GlassDropdown. -->
          <div
            class="absolute top-full right-0 mt-2 w-max max-w-[80vw] max-h-96 overflow-y-auto rounded-2xl border py-2 z-40"
            style="background: var(--menu-bg);
                   border-color: var(--menu-border);
                   box-shadow: var(--menu-shadow);"
          >
            {#each allSkills as sk}
              {@const assigned = assignedIds.has(sk.skill_id)}
              {@const isActive = sk.skill_id === activeSkillId}
              <div
                class="flex items-center px-1 transition whitespace-nowrap
                       {isActive ? 'bg-white/[0.06]' : 'hover:bg-white/[0.04]'}"
              >
                <button
                  type="button"
                  aria-label={assigned ? 'Unassign' : 'Assign'}
                  onclick={(e) => { e.stopPropagation(); toggleAssigned(sk.skill_id) }}
                  class="px-2 py-1 text-sm leading-none text-white/70 hover:text-white transition"
                >
                  {assigned ? '☑' : '☐'}
                </button>
                <button
                  type="button"
                  onclick={() => { selectSkill(sk.skill_id); skillsOpen = false }}
                  class="flex-1 text-left px-2 py-1.5 text-[12px] font-mono text-white/80 hover:text-white transition"
                >
                  {sk.name}
                </button>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </div>
    <div
      class="rounded-2xl border border-white/[0.08] p-4 min-h-[12rem] text-[12px]"
      style="background: var(--glass-bg);
             backdrop-filter: blur(var(--glass-blur));
             -webkit-backdrop-filter: blur(var(--glass-blur));"
    >
      {#if activeSkill}
        {#if activeSkill.description}
          <div class="text-white/50 text-xs mb-3 leading-relaxed">{activeSkill.description}</div>
        {/if}
        <MarkdownBlock text={activeSkill.content ?? ''} />
      {:else if !loading}
        <div class="text-white/40 text-xs">No skill selected.</div>
      {/if}
    </div>
  </section>
</div>

