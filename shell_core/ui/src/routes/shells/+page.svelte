<script>
  // Shells viewer — inspect an assigned shell's rendered boot prompt and
  // toggle which skills are assigned to it. Sticky identity header at the
  // top; accordions for the prompt; a checkbox-popup skill picker that
  // drives the markdown body below. (redline: shared/redlines/Shells Tab.png)
  import { onMount } from 'svelte'
  import {
    getMyShells, getShell, getShellPromptSections,
    getAvailableSkills, getShellSkills, getSkill,
    addShellSkill, removeShellSkill,
  } from '$lib/api.js'
  import MarkdownBlock from '$lib/components/MarkdownBlock.svelte'

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
</script>

<!-- Sticky identity header — sits below TopBar (h-[52px]). The shell
     dropdown IS the name; shortname + role hang underneath. -->
<header class="sticky top-[52px] z-20 bg-surface-1 border-b border-border px-6 py-4 flex flex-col gap-1">
  {#if myShells.length}
    <div class="flex items-baseline gap-3">
      <select class="shell-name-select"
        bind:value={shellId}
        onchange={e => shellId = Number(e.target.value)}>
        {#each myShells as s}
          <option value={s.shell_id}>
            {s.display_name}{s.is_shared ? '  (shared)' : ''}
          </option>
        {/each}
      </select>
      {#if shell?.shortname}
        <span class="text-text-dim text-sm">{shell.shortname}</span>
      {/if}
    </div>
    {#if shell?.role}
      <div class="text-sm"><span class="meta-label">Role:</span> {shell.role}</div>
    {/if}
  {/if}
</header>

<div class="px-6 pt-5 pb-10 flex flex-col gap-5 font-mono">
  {#if error}
    <div class="text-red text-sm">{error}</div>
  {/if}

  <!-- Harness Prompt -->
  <section class="flex flex-col gap-1">
    <h2 class="section-header">Harness Prompt</h2>
    <hr class="border-t border-border" />
    {#if loading && !sections.length}
      <div class="text-text-dim text-xs mt-2">Loading…</div>
    {/if}
    <div class="flex flex-col gap-1 mt-1">
      {#each sections as sec}
        {@const open = openLabels.has(sec.label)}
        <div class="rounded border border-border bg-surface-2">
          <button class="accordion-head" onclick={() => toggle(sec.label)} type="button">
            <span class="caret">{open ? '▾' : '▸'}</span>
            <span class="label">{sec.label}</span>
          </button>
          {#if open}
            <div class="accordion-body">
              <MarkdownBlock text={sec.body} />
            </div>
          {/if}
        </div>
      {/each}
    </div>
  </section>

  <!-- Skill Viewer -->
  <section class="flex flex-col gap-2">
    <div class="flex items-center gap-3">
      <h2 class="section-header shrink-0">Skill Viewer</h2>
      <div class="relative" bind:this={skillBtnRef}>
        <button type="button" class="skill-picker"
          onclick={() => skillsOpen = !skillsOpen}>
          <span class="picker-label">
            {activeSkill?.name ?? (allSkills.length ? 'Select a skill' : '—')}
          </span>
          <span class="picker-caret">{skillsOpen ? '▴' : '▾'}</span>
        </button>
        {#if skillsOpen && allSkills.length}
          <div class="skill-menu">
            {#each allSkills as sk}
              {@const assigned = assignedIds.has(sk.skill_id)}
              <div class="skill-row" class:row-active={sk.skill_id === activeSkillId}>
                <button type="button" class="skill-check"
                  aria-label={assigned ? 'Unassign' : 'Assign'}
                  onclick={(e) => { e.stopPropagation(); toggleAssigned(sk.skill_id) }}>
                  {assigned ? '☑' : '☐'}
                </button>
                <button type="button" class="skill-name"
                  onclick={() => { selectSkill(sk.skill_id); skillsOpen = false }}>
                  {sk.name}
                </button>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </div>
    <hr class="border-t border-border" />
    <div class="rounded border border-border bg-surface-2 p-3 min-h-[12rem]">
      {#if activeSkill}
        {#if activeSkill.description}
          <div class="text-text-dim text-xs mb-2">{activeSkill.description}</div>
        {/if}
        <MarkdownBlock text={activeSkill.content ?? ''} />
      {:else if !loading}
        <div class="text-text-dim text-xs">No skill selected.</div>
      {/if}
    </div>
  </section>
</div>

<style>
  .meta-label {
    color: var(--color-text-dim);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-size: 0.7rem;
    margin-right: 0.35em;
  }
  .section-header {
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--color-text-dim);
  }
  .shell-name-select {
    background: transparent;
    border: 0;
    color: var(--color-text);
    font-family: var(--font-mono);
    font-size: 18px;
    font-weight: 600;
    line-height: 1.2;
    padding: 0 1.2em 0 0;       /* right pad makes room for the native caret */
    cursor: pointer;
    outline: none;
    appearance: none;
    -webkit-appearance: none;
    background-image: linear-gradient(45deg, transparent 50%, var(--color-text-dim) 50%),
                      linear-gradient(135deg, var(--color-text-dim) 50%, transparent 50%);
    background-position: calc(100% - 14px) 55%, calc(100% - 8px) 55%;
    background-size: 6px 6px;
    background-repeat: no-repeat;
  }
  .shell-name-select option {
    background: var(--color-surface-2);
    color: var(--color-text);
    font-size: 13px;
    font-weight: 400;
  }

  .accordion-head {
    display: flex; align-items: center; gap: 0.5rem;
    width: 100%; background: transparent; border: 0;
    padding: 8px 12px;
    color: var(--color-text);
    font-family: var(--font-mono);
    font-size: 12px; font-weight: 600; letter-spacing: 0.04em;
    cursor: pointer; text-align: left;
  }
  .accordion-head:hover { background: var(--color-surface-3); }
  .caret { color: var(--color-text-dim); width: 0.75rem; }
  .label { text-transform: uppercase; }
  .accordion-body {
    padding: 10px 14px 12px;
    border-top: 1px solid var(--color-border);
    font-size: 12px;
  }

  /* Skill picker — custom popup with checkbox + name per row. */
  .skill-picker {
    display: flex; align-items: center; gap: 0.5rem;
    min-width: 18rem;
    background: var(--color-surface-2);
    border: 1px solid var(--color-border);
    color: var(--color-text);
    font-family: var(--font-mono);
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 3px;
    cursor: pointer;
    text-align: left;
  }
  .picker-label { flex: 1; }
  .picker-caret { color: var(--color-text-dim); }
  .skill-menu {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    min-width: 100%;
    max-height: 24rem;
    overflow-y: auto;
    background: var(--color-surface-2);
    border: 1px solid var(--color-border);
    border-radius: 3px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.4);
    z-index: 40;
    padding: 4px 0;
  }
  .skill-row {
    display: flex; align-items: center;
    padding: 0 4px;
  }
  .skill-row:hover { background: var(--color-surface-3); }
  .row-active { background: var(--color-surface-3); }
  .skill-check {
    background: transparent; border: 0;
    color: var(--color-text);
    font-size: 14px;
    cursor: pointer;
    padding: 4px 8px;
    line-height: 1;
  }
  .skill-check:hover { color: var(--color-accent); }
  .skill-name {
    flex: 1;
    background: transparent; border: 0;
    color: var(--color-text);
    font-family: var(--font-mono);
    font-size: 12px;
    text-align: left;
    padding: 5px 8px;
    cursor: pointer;
  }
  .skill-name:hover { color: var(--color-accent); }
</style>
