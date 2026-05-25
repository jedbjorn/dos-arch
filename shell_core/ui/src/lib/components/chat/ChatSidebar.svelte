<script>
  // Browser-chat sidebar (CC-59) — an always-docked panel occupying the right
  // half of the window. dos-arch is a chat-first interface; this is its
  // primary surface.
  //
  // Layout (redline: chat sidebar.png):
  //   - Available Models — providers grouped, click to switch the
  //     conversation's pinned model (PATCHes chat_sessions.model_id).
  //   - Chat — shell header + skills, message list, compose (stop/clear/send).
  //
  // This component is an orchestrator: it owns the session lifecycle, the
  // polling timer, and the cross-component state. The pieces (shell picker,
  // model picker, skills popover, message list, compose box) live in
  // sibling files in lib/components/chat/.
  import { onDestroy, tick } from 'svelte'
  import {
    getMyShells, activateShell, getShellChat, getShellChatSession,
    createShellChatSession, postShellChat, clearShellSession, setSessionModel,
    routeModelToAgents,
  } from '$lib/api.js'
  import { defaultModelId as pickDefaultModel } from '$lib/chat/models.js'
  import { chatModels, refreshModels } from '$lib/chat/modelsStore.js'
  import { computeChatTokens } from '$lib/chat/tokens.js'

  import ShellSwitcher  from './ShellSwitcher.svelte'
  import ModelPicker    from './ModelPicker.svelte'
  import SkillsPopover  from './SkillsPopover.svelte'
  import MessageList    from './MessageList.svelte'
  import ComposeBox     from './ComposeBox.svelte'

  const POLL_MS = 30_000

  let myShells      = $state([])
  let switching     = $state(false)
  let SHELL_ID      = $state(null)

  let selectedModel = $state('')

  let messages      = $state([])
  let chatSessionId = $state(null)
  let sending       = $state(false)
  let waiting       = $state(false)
  let sendError     = $state(false)
  let retryText     = $state('')
  let clearedAt     = $state(0)

  // Bindable surfaces from the child components.
  let draft         = $state('')
  let inputEl      = $state(null)
  let atBottom      = $state(true)
  let scrollToBottom = $state(() => {})

  const activeShell   = $derived(myShells.find(s => s.shell_id === SHELL_ID))
  const shellName     = $derived(activeShell?.display_name ?? 'Shell')
  const activeModel   = $derived($chatModels.find(m => String(m.model_id) === selectedModel))
  const contextWindow = $derived(activeModel?.context_window ?? null)
  const chatTokens    = $derived(computeChatTokens(messages))

  // ── Session lifecycle ─────────────────────────────────────────────────
  function adoptSession(session) {
    chatSessionId = session?.chat_session_id ?? null
    selectedModel = session?.model_id != null ? String(session.model_id) : ''
    return chatSessionId
  }

  async function startNewSession() {
    // Born with the model already in use — fall back to the default only
    // on first use. Passing the model at creation (not a follow-up PATCH)
    // keeps the dialect right from turn one.
    const modelId = selectedModel ? Number(selectedModel) : pickDefaultModel($chatModels)
    return adoptSession(await createShellChatSession(SHELL_ID, modelId))
  }

  async function ensureSession() {
    if (chatSessionId) return chatSessionId
    if (!SHELL_ID) return null
    try {
      const existing = await getShellChatSession(SHELL_ID)
      return existing ? adoptSession(existing) : await startNewSession()
    } catch {}
    return chatSessionId
  }

  // ── Load + poll ───────────────────────────────────────────────────────
  async function load() {
    if (!SHELL_ID) return
    try {
      // Follow a server-side session change — a token auto-clear retires the
      // session and opens a fresh one; adopt whatever is active now.
      const active = await getShellChatSession(SHELL_ID)
      if (active && active.chat_session_id !== chatSessionId) adoptSession(active)
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

  const timer = setInterval(async () => {
    await load()
    await tick(); if (atBottom) scrollToBottom()
  }, POLL_MS)

  onDestroy(() => clearInterval(timer))

  // ── User actions ──────────────────────────────────────────────────────
  async function switchShell(id) {
    if (id === SHELL_ID || switching) return
    switching = true
    try {
      SHELL_ID = id
      messages = []; chatSessionId = null; waiting = false
      sendError = false; retryText = ''
      // Re-target so the dispatcher follows the switch.
      try { await activateShell(id) } catch {}
      // A shell switch begins a fresh chat — new session, fresh BOOT (decision #123).
      await startNewSession()
      await load()
      await tick(); scrollToBottom()
    } catch {}
    switching = false
  }

  async function changeModel(value) {
    selectedModel = value
    const sid = await ensureSession()
    if (!sid) return
    try {
      await setSessionModel(SHELL_ID, sid, value === '' ? null : Number(value))
      await load()  // surface the model-switch marker message immediately
    } catch {}
  }

  async function newChat() {
    if (chatSessionId) { try { await clearShellSession(SHELL_ID, chatSessionId) } catch {} }
    const ids = messages.map(m => m.message_id)
    clearedAt = ids.length ? Math.max(...ids) : clearedAt
    messages = []; waiting = false; sendError = false; retryText = ''; chatSessionId = null
    atBottom = true
    await startNewSession()
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
      await tick(); scrollToBottom()
    } catch {
      sendError = true; retryText = text
    } finally {
      sending = false
    }
  }

  function retry() {
    draft = retryText; sendError = false; retryText = ''
    send()
  }

  async function onSkillCommand(cmd) {
    draft = cmd + ' '
    await tick()
    inputEl?.focus()
  }

  // ── Init ──────────────────────────────────────────────────────────────
  async function init() {
    try { myShells = await getMyShells() } catch {}
    // Open on the user's browser_chat shell — the one the dispatcher serves —
    // falling back to the first owned shell if none is flagged.
    if (myShells.length && !SHELL_ID) {
      SHELL_ID = (myShells.find(s => s.browser_chat) ?? myShells[0]).shell_id
    }
    await refreshModels()
    await ensureSession()
    await load()
    await tick(); scrollToBottom()
  }
  init()
</script>

<aside class="chat-sidebar relative z-10 flex shrink-0 mt-[14px] mr-[14px] mb-[14px] ml-[10px] rounded-2xl border border-white/[0.10] overflow-hidden">
  <ModelPicker
    models={$chatModels}
    {selectedModel}
    onChange={changeModel}
    onRouteToAgents={async (model_id) => {
      try { await routeModelToAgents(model_id) } catch {}
      await refreshModels()
    }}
  />

  <div class="flex-1 min-w-0 flex flex-col">
    <div class="relative flex items-center gap-2 h-[52px] px-3 border-b border-white/[0.06]">
      <ShellSwitcher {myShells} shellId={SHELL_ID} disabled={switching} onSwitch={switchShell} />
      <SkillsPopover shellId={SHELL_ID} onCommand={onSkillCommand} />
    </div>

    <MessageList
      {messages} {waiting} {sendError} {shellName}
      onRetry={retry}
      bind:atBottom
      bind:scrollToBottom
    />

    <ComposeBox
      shellId={SHELL_ID} {shellName} {sending}
      hasMessages={messages.length > 0}
      {chatTokens} {contextWindow}
      onSend={send} onClear={newChat}
      bind:draft
      bind:inputEl
    />
  </div>
</aside>

<style>
  /* Width-only rule kept in scoped CSS — Tailwind v4 supports arbitrary
     values but vw + min-width + shrink-0 reads more clearly here.
     The glass surface is composed via Tailwind utilities above plus
     these two style props that don't translate cleanly to utilities. */
  .chat-sidebar {
    width: 50vw;        /* 1/2 window width — redline: chat redline.png */
    min-width: 518px;
    background: var(--glass-bg);
    backdrop-filter: blur(var(--glass-blur));
    -webkit-backdrop-filter: blur(var(--glass-blur));
  }
</style>
