<script>
  // Browser-chat sidebar (CC-59) — an always-docked panel occupying the right
  // third of the window. dos-arch is a chat-first interface; this is its
  // primary surface. Replaces the floating ChatPanel modal.
  //
  // Two inner columns (redline: chat sidebar.png):
  //   - Available Models — models grouped by provider, click to switch the
  //     conversation's model (PATCHes chat_sessions.model_id).
  //   - Chat — shell header + skills, message list, compose (stop/clear/send).
  //
  // `stop` is UI-only — aborting an in-flight turn needs dispatcher support
  // (flag CC-60).
  import { onDestroy, tick } from 'svelte'
  import {
    getModels, getMyShells, getShellChat, getShellChatSession,
    createShellChatSession, postShellChat, clearShellSession,
    setSessionModel, getShellSkills,
  } from '$lib/api.js'
  import MarkdownBlock from './MarkdownBlock.svelte'

  const POLL_MS           = 30_000
  const MAX_INBOUND_CHARS = 10_000  // mirrors the API gate in routers/shells.py

  // Available-models column: providers in display order.
  const PROVIDERS = [
    { key: 'anthropic', label: 'Anthropic' },
    { key: 'openai',    label: 'OpenAI' },
    { key: 'local',     label: 'Local' },
  ]

  let myShells      = $state([])
  let switching     = $state(false)
  let SHELL_ID      = $state(null)

  let models        = $state([])
  let selectedModel = $state('')    // model_id as string; '' = none pinned

  let messages      = $state([])
  let draft         = $state('')
  let sending       = $state(false)
  let waiting       = $state(false)
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
  const modelsByProvider = $derived(
    Object.fromEntries(PROVIDERS.map(p => [p.key, models.filter(m => m.provider === p.key)]))
  )

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
      await tick(); scrollBottom()
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
    } catch {}
  }

  async function ensureSession() {
    if (chatSessionId) return chatSessionId
    if (!SHELL_ID) return null
    try {
      const session = await getShellChatSession(SHELL_ID) ?? await createShellChatSession(SHELL_ID)
      chatSessionId = session?.chat_session_id ?? null
      selectedModel = session?.model_id != null ? String(session.model_id) : ''
      // A fresh conversation with no model pinned defaults to Claude Sonnet —
      // so the models column always shows a concrete active selection.
      if (chatSessionId && selectedModel === '' && models.length) {
        const def = models.find(m => m.name === 'claude-sonnet-4-6') ?? models[0]
        if (def) await changeModel(String(def.model_id))
      }
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
    await tick(); scrollBottom()
  }, POLL_MS)

  onDestroy(() => {
    clearInterval(timer)
    clearTimeout(hoverTimer)
  })

  async function init() {
    try { myShells = await getMyShells() } catch {}
    if (myShells.length && !SHELL_ID) SHELL_ID = myShells[0].shell_id
    try { models = await getModels() } catch {}
    await ensureSession()
    await load()
    await tick(); scrollBottom()
  }
  init()
</script>

<svelte:window onclick={handleWindowClick} />

<aside class="chat-sidebar">

  <!-- ── Available Models ─────────────────────────────────────────────── -->
  <div class="models-col">
    <div class="col-title">Available Models</div>
    <div class="models-list">
      {#each PROVIDERS as p}
        <div class="provider-group">
          <div class="provider-head">{p.label}</div>
          {#each modelsByProvider[p.key] ?? [] as m}
            <button class="model-row" class:active={String(m.model_id) === selectedModel}
              onclick={() => changeModel(String(m.model_id))}>{m.display_name}</button>
          {/each}
          {#if !(modelsByProvider[p.key] ?? []).length}
            <div class="model-none">(none yet)</div>
          {/if}
        </div>
      {/each}
    </div>
  </div>

  <!-- ── Chat ─────────────────────────────────────────────────────────── -->
  <div class="chat-col">

    <div class="chat-header" bind:this={skillsEl}>
      {#if myShells.length > 1}
        <select class="shell-select" value={SHELL_ID}
          onchange={e => switchShell(Number(e.target.value))} disabled={switching}>
          {#each myShells as s}
            <option value={s.shell_id}>{s.display_name}</option>
          {/each}
        </select>
      {:else}
        <span class="shell-name">{shellName}</span>
      {/if}
      <button class="skills-btn" class:active={showSkills}
        onclick={e => { e.stopPropagation(); toggleSkills() }}>Skills ▾</button>

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
            <button class="clear-yes" onclick={clearChat}>Yes</button>
            <button class="clear-no"  onclick={() => clearConfirm = false}>No</button>
          </div>
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
      <div class="compose-btns">
        <button class="cbtn stop" disabled
          title="Stop an in-flight turn — backend not wired yet (CC-60)">stop</button>
        <button class="cbtn clear" onclick={() => clearConfirm = true}
          disabled={!messages.length}>clear</button>
        <button class="cbtn send" onclick={send}
          disabled={sending || !SHELL_ID || !draft.trim()}>send</button>
      </div>
    </div>
    {#if draft.length > MAX_INBOUND_CHARS * 0.8}
      <div class="compose-meta">
        <span class="char-count" class:at-cap={draft.length >= MAX_INBOUND_CHARS}>
          {draft.length.toLocaleString()} / {MAX_INBOUND_CHARS.toLocaleString()}
        </span>
      </div>
    {/if}

  </div>
</aside>

<style>
  .chat-sidebar {
    width: 33vw;
    min-width: 460px;
    flex-shrink: 0;
    height: 100vh;
    display: flex;
    border-left: 1px solid var(--color-border);
    background: var(--color-surface-1);
  }

  /* ── Available Models column ──────────────────────────────────────────── */
  .models-col {
    width: 132px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--color-border);
    background: var(--color-surface-2);
  }
  .col-title {
    padding: 10px 12px;
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

  /* ── Chat column ──────────────────────────────────────────────────────── */
  .chat-col {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  .chat-header {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    border-bottom: 1px solid var(--color-border);
    background: var(--color-surface-2);
  }
  .shell-name { flex: 1; font-size: 13px; font-weight: 700; color: var(--color-text); letter-spacing: 0.04em; }
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
    outline: none;
  }
  .shell-select option { background: var(--color-surface-2); color: var(--color-text); }
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
    top: 100%; right: 8px;
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

  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 0;
  }
  .empty { color: var(--color-text-dim); font-size: 12px; text-align: center; margin-top: 40px; }

  .msg { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; }
  .msg.outbound { align-items: flex-end; }
  .bubble {
    background: var(--color-surface-2);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 12px;
    color: var(--color-text);
    max-width: 92%;
    word-break: break-word;
    line-height: 1.5;
  }
  .msg.outbound .bubble {
    background: color-mix(in srgb, var(--color-accent) 15%, var(--color-surface-1));
    border-color: color-mix(in srgb, var(--color-accent) 30%, var(--color-border));
  }
  .meta { font-family: var(--font-mono); font-size: 9px; color: var(--color-text-dim); padding: 0 2px; }

  .waiting { display: flex; align-items: flex-end; padding: 6px 2px; align-self: flex-end; }
  .waiting-label { font-family: var(--font-mono); font-size: 9px; color: var(--color-text-dim); }
  .dots::after { content: ''; animation: dots 1.4s steps(4, end) infinite; }
  @keyframes dots {
    0% { content: ''; } 25% { content: '.'; } 50% { content: '..'; }
    75% { content: '...'; } 100% { content: ''; }
  }

  .send-error { display: flex; align-items: center; gap: 8px; align-self: flex-end; padding: 5px 10px; border-radius: 6px; background: rgba(224,85,85,0.08); border: 1px solid rgba(224,85,85,0.2); }
  .error-msg  { font-family: var(--font-mono); font-size: 10px; color: var(--color-red); }
  .retry-btn  { font-family: var(--font-mono); font-size: 10px; font-weight: 600; background: none; border: 1px solid var(--color-accent); border-radius: 4px; color: var(--color-accent); cursor: pointer; padding: 2px 8px; }
  .retry-btn:hover { background: rgba(0,114,255,0.08); }

  .clear-confirm {
    align-self: stretch;
    display: flex; align-items: center; gap: 6px;
    background: var(--color-surface-2); border: 1px solid var(--color-border);
    border-radius: 6px; padding: 6px 10px;
    font-family: var(--font-mono); font-size: 10px; color: var(--color-text-dim);
  }
  .clear-confirm span { flex: 1; }
  .clear-yes { background: none; border: 1px solid var(--color-red); border-radius: 4px; color: var(--color-red); font-family: var(--font-mono); font-size: 10px; cursor: pointer; padding: 2px 8px; }
  .clear-yes:hover { background: rgba(224,85,85,0.15); }
  .clear-no  { background: none; border: 1px solid var(--color-border); border-radius: 4px; color: var(--color-text-dim); font-family: var(--font-mono); font-size: 10px; cursor: pointer; padding: 2px 8px; }
  .clear-no:hover { border-color: var(--color-text-dim); color: var(--color-text); }

  .compose { display: flex; gap: 8px; padding: 8px 12px; background: var(--color-surface-2); border-top: 1px solid var(--color-border); }
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
  .compose-btns { display: flex; flex-direction: column; gap: 4px; justify-content: flex-end; }
  .cbtn {
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.04em;
    border-radius: 4px;
    padding: 3px 10px;
    cursor: pointer;
    border: 1px solid var(--color-border);
    background: var(--color-surface-1);
    color: var(--color-text-dim);
  }
  .cbtn:disabled { opacity: 0.4; cursor: default; }
  .cbtn.send:not(:disabled) { border-color: var(--color-accent); color: var(--color-accent); }
  .cbtn.send:not(:disabled):hover { background: rgba(0,114,255,0.08); }
  .cbtn.clear:not(:disabled):hover { border-color: var(--color-red); color: var(--color-red); }

  .compose-meta { display: flex; justify-content: flex-end; padding: 0 12px 6px; background: var(--color-surface-2); }
  .char-count { font-family: var(--font-mono); font-size: 9px; color: var(--color-text-dim); }
  .char-count.at-cap { color: var(--color-red); }
</style>
