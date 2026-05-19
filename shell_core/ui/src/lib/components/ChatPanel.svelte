<script>
  // Browser-chat panel — ported from designs_os ExpChat (CC-58). A floating
  // modal that polls chat_messages, sends inbound messages, and renders the
  // shell's replies. The model-switch dropdown is the visible surface for the
  // agnostic runtime: picking a model PATCHes chat_sessions.model_id, and the
  // dispatcher routes the next turn to that provider.
  //
  // Dropped from the ExpChat original (no dos-arch equivalent): cost display
  // (tokens-only, decision #108), the VoxelClimb animation, IssueReport, the
  // history-window control, and cross-component trigger events.
  import { onDestroy, tick } from 'svelte'
  import {
    getModels, getMyShells, getShellChat, getShellChatSession,
    createShellChatSession, postShellChat, clearShellSession,
    setSessionModel, getShellSkills,
  } from '$lib/api.js'
  import MarkdownBlock from './MarkdownBlock.svelte'

  const POLL_MS         = 30_000
  const MAX_INBOUND_CHARS = 10_000  // mirrors the API gate in routers/shells.py

  let myShells      = $state([])
  let switching     = $state(false)
  let SHELL_ID      = $state(null)

  let models        = $state([])
  let selectedModel = $state('')    // model_id as string; '' = dispatcher default

  let open          = $state(false)
  let messages      = $state([])
  let draft         = $state('')
  let sending       = $state(false)
  let waiting       = $state(false)
  let lastSeenId    = $state(0)
  let unread        = $state(0)
  let listEl        = $state(null)
  let clearedAt     = $state(0)
  let showSkills    = $state(false)
  let skills        = $state([])
  let inputEl       = $state(null)
  let skillsEl      = $state(null)
  let clearConfirm  = $state(false)
  let chatSessionId = $state(null)
  let sendError     = $state(false)
  let retryText     = $state('')
  let hoverTimer    = $state(null)
  let hoveredDesc   = $state('')
  let hoveredTop    = $state(0)
  let hoveredLeft   = $state(0)

  const activeShell = $derived(myShells.find(s => s.shell_id === SHELL_ID))
  const shellName   = $derived(activeShell?.display_name ?? 'Shell')

  function parseArgs(desc) {
    if (!desc) return ''
    const m = desc.match(/^`([^`]+)`/)
    return m ? m[1] : ''
  }

  function parseRequires(desc) {
    if (!desc) return ''
    const m = desc.match(/Requires[^.]+\./)
    return m ? m[0] : ''
  }

  function handleSkillEnter(e, skill) {
    clearTimeout(hoverTimer)
    const rect = e.currentTarget.getBoundingClientRect()
    hoverTimer = setTimeout(() => {
      hoveredDesc = skill.description || ''
      hoveredTop  = rect.top
      hoveredLeft = rect.left
    }, 600)
  }

  function handleSkillLeave() {
    clearTimeout(hoverTimer)
    hoveredDesc = ''
  }

  async function toggleSkills() {
    showSkills = !showSkills
    if (!showSkills) { clearTimeout(hoverTimer); hoveredDesc = '' }
    if (showSkills && skills.length === 0 && SHELL_ID) {
      try { skills = await getShellSkills(SHELL_ID) } catch {}
    }
  }

  async function switchShell(id) {
    if (id === SHELL_ID || switching) return
    switching = true
    try {
      SHELL_ID = id
      messages = []; chatSessionId = null; waiting = false
      sendError = false; retryText = ''; clearConfirm = false; skills = []
      await ensureSession()
      await load()
      if (open) { await tick(); scrollBottom() }
    } catch {}
    switching = false
  }

  function handleWindowClick(e) {
    if (!showSkills) return
    if (skillsEl && !skillsEl.contains(e.target)) showSkills = false
  }

  async function load() {
    if (!SHELL_ID) return
    try {
      const prev = messages
      const msgs = await getShellChat(SHELL_ID)
      messages = msgs.filter(m => m.message_id > clearedAt && m.chat_session_id === chatSessionId)
      if (waiting) {
        const hadReply = msgs.some(m => m.direction === 'outbound' &&
          (!prev.length || m.message_id > Math.max(...prev.map(p => p.message_id))))
        if (hadReply) waiting = false
      }
      if (!open) {
        unread = msgs.filter(m => m.direction === 'outbound' && m.message_id > lastSeenId).length
      }
    } catch {}
  }

  async function ensureSession() {
    if (chatSessionId) return chatSessionId
    if (!SHELL_ID) return null
    try {
      const session = await getShellChatSession(SHELL_ID) ?? await createShellChatSession(SHELL_ID)
      chatSessionId = session?.chat_session_id ?? null
      selectedModel = session?.model_id != null ? String(session.model_id) : ''
    } catch {}
    return chatSessionId
  }

  async function changeModel(value) {
    selectedModel = value
    const sid = await ensureSession()
    if (!sid) return
    try { await setSessionModel(SHELL_ID, sid, value === '' ? null : Number(value)) } catch {}
  }

  async function clearChat() {
    clearConfirm = false
    if (chatSessionId) { try { await clearShellSession(SHELL_ID, chatSessionId) } catch {} }
    const ids = messages.map(m => m.message_id)
    clearedAt = ids.length ? Math.max(...ids) : clearedAt
    messages = []; waiting = false; sendError = false; retryText = ''; chatSessionId = null
    await ensureSession()
  }

  function markRead() {
    if (messages.length) lastSeenId = Math.max(...messages.map(m => m.message_id))
    unread = 0
  }

  async function toggleOpen() {
    open = !open
    if (open) {
      await ensureSession(); await load(); markRead()
      await tick(); scrollBottom()
    }
  }

  async function send() {
    const text = draft.trim()
    if (!text || sending || !SHELL_ID) return
    sending = true; sendError = false; retryText = ''; draft = ''
    try {
      const sid = await ensureSession()
      const msg = await postShellChat(SHELL_ID, text, sid)
      messages = [...messages, { ...msg, chat_session_id: sid }]
      waiting = true
      await tick(); scrollBottom()
    } catch {
      sendError = true; retryText = text
    } finally {
      sending = false
    }
  }

  function retry() { draft = retryText; sendError = false; retryText = ''; send() }

  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  function scrollBottom() { if (listEl) listEl.scrollTop = listEl.scrollHeight }

  const timer = setInterval(async () => {
    await load()
    if (open) { await tick(); scrollBottom() }
  }, POLL_MS)

  onDestroy(() => {
    clearInterval(timer)
    clearTimeout(hoverTimer)
  })

  async function init() {
    try { myShells = await getMyShells() } catch {}
    if (myShells.length && !SHELL_ID) SHELL_ID = myShells[0].shell_id
    try { models = await getModels() } catch {}
    await load()
  }
  init()
</script>

<svelte:window onclick={handleWindowClick} />

<div class="wrap">
  {#if open}
    <div class="panel">

      <div class="header" bind:this={skillsEl}>
        {#if myShells.length > 1}
          <select class="shell-select" value={SHELL_ID}
            onchange={e => switchShell(Number(e.target.value))}
            disabled={switching}>
            {#each myShells as s}
              <option value={s.shell_id}>{s.display_name}</option>
            {/each}
          </select>
        {:else}
          <span class="title">{shellName}</span>
        {/if}

        <select class="model-select" value={selectedModel}
          onchange={e => changeModel(e.target.value)}
          title="Model for this conversation — switches the next turn's provider">
          <option value="">Default</option>
          {#each models as m}
            <option value={String(m.model_id)}>{m.display_name}</option>
          {/each}
        </select>

        <button class="skills-btn" class:active={showSkills}
          onclick={e => { e.stopPropagation(); toggleSkills() }}>Skills</button>
        <button class="close-x" onclick={toggleOpen}>✕</button>

        {#if showSkills}
          <div class="skills-popover">
            {#if skills.length === 0}
              <div class="skills-empty">No skills assigned.</div>
            {:else}
              {#each skills as skill}
                <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
                <div class="skill-row" class:clickable={!!skill.command}
                  onmouseenter={e => handleSkillEnter(e, skill)}
                  onmouseleave={handleSkillLeave}
                  onclick={skill.command ? async () => {
                    draft = skill.command + ' '
                    showSkills = false
                    clearTimeout(hoverTimer); hoveredDesc = ''
                    await tick(); inputEl?.focus()
                  } : null}>
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

      <div class="messages" bind:this={listEl}>
        {#if messages.length === 0}
          <div class="empty">No messages yet.</div>
        {:else}
          {#each messages as msg (msg.message_id)}
            <div class="msg" class:outbound={msg.direction === 'outbound'}>
              <div class="bubble"><MarkdownBlock text={msg.body} /></div>
              <div class="meta">
                {msg.sent_at?.slice(0, 16).replace('T', ' ')}
                {#if msg.direction === 'outbound' && msg.tokens != null}
                  &nbsp;{msg.tokens.toLocaleString()} tok
                {:else if msg.direction === 'inbound'}
                  &nbsp;~{Math.ceil((msg.body?.length ?? 0) / 4).toLocaleString()} tok
                {/if}
              </div>
            </div>
          {/each}

          {#if waiting}
            <div class="waiting">
              <span class="waiting-label">{shellName} is thinking<span class="dots"></span></span>
            </div>
          {/if}

          {#if sendError}
            <div class="send-error">
              <span class="error-msg">Failed to send</span>
              <button class="retry-btn" onclick={retry}>Retry</button>
            </div>
          {/if}

          {#if clearConfirm}
            <div class="clear-confirm">
              <span>Clear this conversation?</span>
              <button class="clear-yes" onclick={clearChat}>Yes — clear</button>
              <button class="clear-no"  onclick={() => clearConfirm = false}>No</button>
            </div>
          {:else}
            <button class="clear-btn" onclick={() => clearConfirm = true}>Clear</button>
          {/if}
        {/if}
      </div>

      <div class="compose">
        <textarea
          class="input"
          bind:this={inputEl}
          placeholder={SHELL_ID ? `Message ${shellName}…` : 'No shell assigned'}
          rows="3"
          bind:value={draft}
          onkeydown={onKey}
          maxlength={MAX_INBOUND_CHARS}
          disabled={!SHELL_ID}
        ></textarea>
        <button class="send-btn" onclick={send}
          disabled={sending || !SHELL_ID || !draft.trim()}
          title="Send message">
          <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="m60.4351 3.564a2.9686 2.9686 0 0 0 -3.1651-.6905l-45.27 16.8179a3.0114 3.0114 0 0 0 .1509 5.6763l19.6821 6.144a1.86 1.86 0 0 1 .4087.2471s28.5814-27.8229 28.1934-28.1948z" fill="#26a6fe"/>
            <path d="m60.436 3.5649c-.3719-.388-28.196 28.1934-28.196 28.1934a1.8659 1.8659 0 0 1 .2481.41l6.1442 19.6817a3.0154 3.0154 0 0 0 5.6763.1509l16.8179-45.27a2.9711 2.9711 0 0 0 -.6905-3.166z" fill="#1c82ba"/>
            <path d="m29.3887 36.0254-22 22c-.9051.9332-2.343-.5108-1.4141-1.4141l22-22a1 1 0 0 1 1.4141 1.4141z" fill="#eee"/>
            <path d="m32.3887 46.0254-15 15c-.9051.9332-2.343-.5108-1.4141-1.4141l15-15a1 1 0 0 1 1.4141 1.4141z" fill="#eee"/>
            <path d="m19.3887 33.0254-15 15c-.9051.9332-2.343-.5108-1.4141-1.4141l15-15a1 1 0 0 1 1.4141 1.4141z" fill="#eee"/>
          </svg>
        </button>
      </div>
      {#if draft.length > MAX_INBOUND_CHARS * 0.8}
        <div class="compose-meta">
          <span class="char-count" class:at-cap={draft.length >= MAX_INBOUND_CHARS}>
            {draft.length.toLocaleString()} / {MAX_INBOUND_CHARS.toLocaleString()}
          </span>
        </div>
      {/if}

    </div>
  {/if}

  <button class="fab" onclick={toggleOpen} title="Chat with {shellName}">
    {shellName}
    {#if unread > 0}<span class="badge">{unread}</span>{/if}
  </button>
</div>

<style>
  .wrap {
    position: fixed;
    top: 64px; right: 12px; bottom: 12px;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: flex-end;
    gap: 12px;
  }

  .fab {
    background: transparent;
    color: var(--color-accent);
    border: 1px solid var(--color-accent);
    border-radius: 20px;
    padding: 8px 18px;
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.04em;
    cursor: pointer;
    position: relative;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    transition: background 150ms, color 150ms;
  }
  .fab:hover { background: var(--color-accent); color: #fff; }

  .badge {
    position: absolute;
    top: -6px; right: -6px;
    background: var(--color-red);
    color: #fff;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    padding: 1px 5px;
    line-height: 1.4;
  }

  .panel {
    width: 400px;
    flex: 1;
    min-height: 0;
    background: var(--color-surface-1);
    border: 1px solid var(--color-border);
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    box-shadow: 0 4px 24px rgba(0,0,0,0.35);
    overflow: hidden;
  }

  .header {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--color-border);
    background: var(--color-surface-2);
  }
  .title { flex: 1; font-size: 13px; font-weight: 700; color: var(--color-text); letter-spacing: 0.04em; }

  .shell-select {
    flex: 1;
    background: transparent;
    border: none;
    color: var(--color-text);
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.04em;
    cursor: pointer;
    padding: 0;
    appearance: none;
    outline: none;
  }
  .shell-select:disabled { opacity: 0.5; cursor: default; }
  .shell-select option { background: var(--color-surface-2); color: var(--color-text); }

  .model-select {
    background: var(--color-surface-1);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    color: var(--color-text-dim);
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.04em;
    cursor: pointer;
    padding: 2px 4px;
    outline: none;
  }
  .model-select:focus { border-color: var(--color-accent); }
  .model-select option { background: var(--color-surface-2); color: var(--color-text); }

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

  .close-x {
    background: none;
    border: none;
    color: var(--color-text-dim);
    cursor: pointer;
    font-size: 12px;
    padding: 0;
    line-height: 1;
  }
  .close-x:hover { color: var(--color-text); }

  .skills-popover {
    position: absolute;
    top: 100%; right: 8px;
    width: 250px;
    background: var(--color-surface-2);
    border: 1px solid var(--color-border);
    border-top: none;
    border-radius: 0 0 8px 8px;
    z-index: 10;
    max-height: 460px;
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

  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 0;
  }
  .empty { color: var(--color-text-dim); font-size: 12px; text-align: center; margin-top: 40px; font-family: var(--font-mono); }

  .msg { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; }
  .msg.outbound { align-items: flex-end; }
  .bubble {
    background: var(--color-surface-2);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 12px;
    color: var(--color-text);
    max-width: 90%;
    word-break: break-word;
    line-height: 1.5;
  }
  .msg.outbound .bubble {
    background: color-mix(in srgb, var(--color-accent) 15%, var(--color-surface-1));
    border-color: color-mix(in srgb, var(--color-accent) 30%, var(--color-border));
  }
  .meta { font-family: var(--font-mono); font-size: 9px; color: var(--color-text-dim); padding: 0 2px; }

  .waiting {
    display: flex;
    align-items: flex-end;
    padding: 6px 2px;
    align-self: flex-end;
  }
  .waiting-label { font-family: var(--font-mono); font-size: 9px; color: var(--color-text-dim); }
  .dots::after {
    content: '';
    animation: dots 1.4s steps(4, end) infinite;
  }
  @keyframes dots {
    0%   { content: ''; }
    25%  { content: '.'; }
    50%  { content: '..'; }
    75%  { content: '...'; }
    100% { content: ''; }
  }

  .send-error { display: flex; align-items: center; gap: 8px; align-self: flex-end; padding: 5px 10px; border-radius: 6px; background: rgba(224,85,85,0.08); border: 1px solid rgba(224,85,85,0.2); }
  .error-msg  { font-family: var(--font-mono); font-size: 10px; color: var(--color-red); }
  .retry-btn  { font-family: var(--font-mono); font-size: 10px; font-weight: 600; background: none; border: 1px solid var(--color-accent); border-radius: 4px; color: var(--color-accent); cursor: pointer; padding: 2px 8px; }
  .retry-btn:hover { background: rgba(0,114,255,0.08); }

  .clear-btn {
    align-self: flex-end;
    background: none; border: none; color: var(--color-text-dim);
    font-family: var(--font-mono); font-size: 10px; cursor: pointer;
    padding: 2px 4px; opacity: 0.5; margin-top: 4px;
  }
  .clear-btn:hover { opacity: 1; color: var(--color-red); }

  .clear-confirm {
    align-self: stretch;
    display: flex; align-items: center; gap: 6px;
    background: var(--color-surface-2); border: 1px solid var(--color-border);
    border-radius: 6px; padding: 6px 10px; margin-top: 6px;
    font-family: var(--font-mono); font-size: 10px; color: var(--color-text-dim);
  }
  .clear-confirm span { flex: 1; }
  .clear-yes { background: none; border: 1px solid var(--color-red); border-radius: 4px; color: var(--color-red); font-family: var(--font-mono); font-size: 10px; cursor: pointer; padding: 2px 8px; }
  .clear-yes:hover { background: rgba(224,85,85,0.15); }
  .clear-no  { background: none; border: 1px solid var(--color-border); border-radius: 4px; color: var(--color-text-dim); font-family: var(--font-mono); font-size: 10px; cursor: pointer; padding: 2px 8px; }
  .clear-no:hover { border-color: var(--color-text-dim); color: var(--color-text); }

  .compose { display: flex; gap: 6px; padding: 8px 10px; background: var(--color-surface-2); align-items: flex-end; }
  .input {
    flex: 1;
    background: var(--color-surface-1);
    border: 1px solid var(--color-border);
    border-radius: 6px;
    color: var(--color-text);
    font-family: var(--font-mono);
    font-size: 12px;
    padding: 6px 8px;
    resize: none;
    line-height: 1.4;
  }
  .input:focus { outline: none; border-color: var(--color-accent); }
  .send-btn {
    width: 20px; height: 20px; padding: 0;
    background: none; border: none; cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center;
    transition: transform 0.12s, opacity 0.12s;
  }
  .send-btn svg { width: 18px; height: 18px; display: block; }
  .send-btn:disabled { opacity: 0.35; cursor: default; }
  .send-btn:not(:disabled):hover { transform: translateY(-1px); }

  .compose-meta {
    display: flex; justify-content: flex-end;
    padding: 0 12px 8px; background: var(--color-surface-2);
  }
  .char-count {
    font-family: var(--font-mono); font-size: 9px;
    color: var(--color-text-dim); white-space: nowrap;
  }
  .char-count.at-cap { color: var(--color-red); }
</style>
