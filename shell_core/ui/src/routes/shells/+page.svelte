<script>
  // Shells viewer — inspect an assigned shell's rendered boot prompt and
  // toggle which skills are assigned to it. Sticky identity sub-header
  // below the TopBar; glass-panel sections for the prompt accordions and
  // skill viewer. (redline: shared/redlines/Shells Tab.png)
  import { onMount } from 'svelte'
  import {
    getMyShells, getShell, getShellPromptSections, putShellPromptSection,
    getAvailableSkills, getShellSkills, getSkill, updateSkill,
    addShellSkill, removeShellSkill, promptRenderUrl,
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

  // Dialect for the prompt-render download — TOOLS and OUTPUT SHAPE are the
  // only sections it changes. Defaults to anthropic to match the API.
  let downloadDialect = $state('anthropic')

  // Unified edit modal — one body editor for prompt-section blocks and skill
  // content. Null = closed. Open shape: { title, draft, saving, save() }.
  let editModal = $state(null)

  // Rough token estimator — BPE-ish, ~15% off for English; the tilde in the
  // header makes the approximation explicit. No bundled tokenizer.
  function approxTokens(s) { return Math.ceil((s?.length ?? 0) / 4) }

  // Reparent an element to document.body. The shells page mounts inside a
  // `relative z-10` wrapper that creates a stacking context, trapping any
  // child z-index. Modals need to escape that context to paint above the
  // ChatSidebar sibling (which lives in the parent stacking context).
  function portal(node) {
    document.body.appendChild(node)
    return { destroy() { node.parentNode?.removeChild(node) } }
  }

  async function loadShellData(id) {
    if (!id) return
    loading = true
    error = ''
    openLabels = new Set()
    editModal = null
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
    if (editModal?.kind === 'skill') editModal = null
    try {
      activeSkill = await getSkill(skill_id)
    } catch (e) {
      activeSkill = null
      error = String(e.message ?? e)
    }
  }

  function openSectionEdit(sec) {
    error = ''
    editModal = {
      kind:   'section',
      title:  sec.label,
      draft:  sec.body ?? '',
      saving: false,
      save:   async () => {
        if (!shellId) return
        editModal.saving = true
        try {
          await putShellPromptSection(shellId, sec.label, editModal.draft)
          sections  = await getShellPromptSections(shellId)
          editModal = null
        } catch (e) {
          error = String(e.message ?? e)
          editModal.saving = false
        }
      },
    }
  }

  function openSkillEdit() {
    if (!activeSkill) return
    error = ''
    editModal = {
      kind:   'skill',
      title:  activeSkill.name,
      draft:  activeSkill.content ?? '',
      saving: false,
      save:   async () => {
        editModal.saving = true
        try {
          await updateSkill(activeSkill.skill_id, { content: editModal.draft })
          activeSkill = await getSkill(activeSkill.skill_id)
          editModal   = null
        } catch (e) {
          error = String(e.message ?? e)
          editModal.saving = false
        }
      },
    }
  }

  function closeModal() {
    if (editModal?.saving) return  // don't yank state mid-save
    editModal = null
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

  // Harness Prompt is split into two groups — General (universal — same body
  // for every shell; edits should fan out) and Shell Specific (derived from
  // this shell's row, assignments, or runtime). Within each group the API's
  // render order is preserved so the boot composition stays legible.
  const groupedSections = $derived([
    { title: 'General',        items: sections.filter(s => s.scope === 'universal') },
    { title: 'Shell Specific', items: sections.filter(s => s.scope === 'shell') },
  ])

  // Aggregate stats — full rendered harness (sum of every section body) and
  // the currently-displayed skill. Reuses approxTokens.
  const harnessChars  = $derived(sections.reduce((n, s) => n + (s.body?.length ?? 0), 0))
  const harnessTokens = $derived(approxTokens(sections.map(s => s.body ?? '').join('')))
  const skillChars    = $derived(activeSkill?.content?.length ?? 0)
  const skillTokens   = $derived(approxTokens(activeSkill?.content ?? ''))
</script>

<!-- Sticky identity sub-header — sits below the TopBar (h-[52px]).
     Glass backdrop so content scrolls cleanly under it. -->
<header
  class="sticky top-0 z-20 px-6 py-4 flex flex-col gap-1 border-b border-white/[0.08]"
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
    <div class="flex items-center justify-between px-1">
      <h2 class="text-[10px] uppercase tracking-[0.15em] text-white/40">Harness Prompt</h2>
      {#if shellId}
        <div class="flex items-center gap-3">
          <GlassDropdown
            value={downloadDialect}
            items={[
              { value: 'anthropic', label: 'anthropic' },
              { value: 'openai',    label: 'openai'    },
              { value: 'parsed',    label: 'parsed'    },
            ]}
            onChange={(v) => (downloadDialect = v)}
            align="right"
          />
          <a
            href={promptRenderUrl(shellId, downloadDialect)}
            download
            title="Download full rendered prompt"
            aria-label="Download full rendered prompt"
            class="text-white/40 hover:text-white text-xs leading-none px-1 transition"
          >↓</a>
        </div>
      {/if}
    </div>
    <div class="flex items-baseline gap-4 px-1 text-[10px] uppercase tracking-[0.15em]">
      <span class="text-white/30">Char Count <span class="text-white/60">{harnessChars.toLocaleString()}</span></span>
      <span class="text-white/30">Est. Tokens <span class="text-white/60">~{harnessTokens.toLocaleString()}</span></span>
    </div>
    <div
      class="rounded-2xl border border-white/[0.08] overflow-hidden"
      style="background: var(--glass-bg);
             backdrop-filter: blur(var(--glass-blur));
             -webkit-backdrop-filter: blur(var(--glass-blur));"
    >
      {#if loading && !sections.length}
        <div class="text-white/40 text-xs px-4 py-3">Loading…</div>
      {/if}
      {#each groupedSections as group, gi}
        {#if group.items.length}
          <div
            class="px-4 py-1.5 text-[10px] uppercase tracking-[0.15em] text-white/40 bg-white/[0.02]
                   {gi > 0 ? 'border-t border-white/[0.06]' : ''}"
          >
            {group.title}
          </div>
          {#each group.items as sec}
            {@const open = openLabels.has(sec.label)}
            <div class="border-t border-white/[0.06]">
              <button
                type="button"
                onclick={() => toggle(sec.label)}
                class="w-full flex items-center gap-2 px-4 py-2.5 text-left text-[12px] font-mono font-semibold tracking-wider text-white/90 hover:bg-white/[0.03] transition"
              >
                <span class="text-white/40 w-3 text-xs">{open ? '▾' : '▸'}</span>
                <span class="uppercase">{sec.label}</span>
              </button>
              {#if open}
                <div class="px-5 pb-4 pt-3 border-t border-white/[0.06] text-[12px] relative">
                  <!-- Pencil opens the edit modal; hidden for non-editable
                       sections (LAWS, pickers, append-only, BOOT, etc). -->
                  {#if sec.editable}
                    <button
                      type="button"
                      aria-label="Edit"
                      title="Edit"
                      onclick={() => openSectionEdit(sec)}
                      class="absolute top-2 right-3 px-2 py-0.5 text-white/40 hover:text-white text-xs leading-none transition"
                    >✎</button>
                  {/if}
                  <MarkdownBlock text={sec.body} />
                </div>
              {/if}
            </div>
          {/each}
        {/if}
      {/each}
    </div>
  </section>

  <!-- Skill Viewer — header row + glass-panel body. -->
  <section class="flex flex-col gap-2">
    <div class="flex items-center gap-3 px-1">
      <h2 class="text-[10px] uppercase tracking-[0.15em] text-white/40 shrink-0">Skill Viewer</h2>
      <div class="relative" bind:this={skillBtnRef}>
        <button
          type="button"
          onclick={() => skillsOpen = !skillsOpen}
          class="flex items-center gap-2 w-40 px-3 py-1.5 rounded-full border text-xs transition
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
            class="absolute top-full left-0 mt-2 w-max max-w-[80vw] max-h-96 overflow-y-auto rounded-2xl border py-2 z-40"
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
      <!-- Right-aligned edit affordance — opens the unified edit modal. -->
      {#if activeSkill}
        <button
          type="button"
          aria-label="Edit"
          title="Edit skill content"
          onclick={openSkillEdit}
          class="ml-auto px-2 py-0.5 text-white/40 hover:text-white text-xs leading-none transition"
        >✎</button>
      {/if}
    </div>
    <div class="flex items-baseline gap-4 px-1 text-[10px] uppercase tracking-[0.15em]">
      <span class="text-white/30">Char Count <span class="text-white/60">{skillChars.toLocaleString()}</span></span>
      <span class="text-white/30">Est. Tokens <span class="text-white/60">~{skillTokens.toLocaleString()}</span></span>
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

<!-- Unified edit modal — 650×700, fixed dialog with an overlay that cancels
     on click. Save bottom-left, Cancel bottom-right per spec. Header carries
     the display name + a live ~tokens / chars readout. -->
{#if editModal}
  <div
    use:portal
    class="fixed inset-0 z-50 flex items-center justify-center"
    style="background: rgba(0,0,0,0.55);"
    onmousedown={closeModal}
    role="presentation"
  >
    <div
      class="flex flex-col rounded-2xl border border-white/[0.10] shadow-2xl"
      style="width: 650px; height: 700px; background: var(--menu-bg);"
      onmousedown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      aria-label={editModal.title}
      tabindex="-1"
    >
      <!-- Header — subheading-styled name on the left, live counter on the right. -->
      <div class="flex items-center justify-between px-5 pt-4 pb-3 border-b border-white/[0.08]">
        <div class="text-sm font-medium text-white/90 truncate pr-3">{editModal.title}</div>
        <div class="text-[11px] font-mono text-white/40 shrink-0">
          ~{approxTokens(editModal.draft).toLocaleString()} tokens
          / {editModal.draft.length.toLocaleString()} chars
        </div>
      </div>
      <!-- Body — single textarea fills the remaining height. -->
      <div class="flex-1 min-h-0 p-4">
        <!-- svelte-ignore a11y_autofocus -->
        <textarea
          bind:value={editModal.draft}
          disabled={editModal.saving}
          autofocus
          class="w-full h-full px-3 py-2 rounded-lg bg-black/30 border border-white/[0.08] focus:border-white/20 focus:outline-none text-[12px] font-mono text-white/90 resize-none"
        ></textarea>
      </div>
      <!-- Footer — Save bottom-LEFT, Cancel bottom-RIGHT (per spec). -->
      <div class="flex items-center justify-between px-5 pb-4 pt-2">
        <button
          type="button"
          onclick={editModal.save}
          disabled={editModal.saving}
          class="px-4 py-1.5 rounded-full text-xs font-medium border border-white/20 text-white hover:bg-white/[0.06] transition disabled:opacity-40"
        >{editModal.saving ? 'Saving…' : 'Save'}</button>
        <button
          type="button"
          onclick={closeModal}
          disabled={editModal.saving}
          class="px-4 py-1.5 rounded-full text-xs text-white/70 hover:text-white border border-white/[0.10] hover:border-white/20 transition disabled:opacity-40"
        >Cancel</button>
      </div>
    </div>
  </div>
{/if}

