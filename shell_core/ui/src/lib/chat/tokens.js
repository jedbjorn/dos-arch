// Inbound message char cap — mirrors the API gate in routers/shells.py.
export const MAX_INBOUND_CHARS = 10_000

// Live context-window estimate. Each completed turn's outbound message
// carries that turn's total (input + output); every turn's input
// re-includes the whole history, so the latest outbound count *is* the
// current context — earlier turns are not summed. An inbound message
// that hasn't been answered yet adds a rough ~chars/4 estimate.
export function computeChatTokens(messages) {
  let ctx = 0, pending = 0
  for (const m of messages) {
    if (m.direction === 'outbound' && m.tokens != null) {
      ctx = m.tokens
      pending = 0
    } else {
      pending += Math.ceil((m.body?.length ?? 0) / 4)
    }
  }
  return ctx + pending
}
