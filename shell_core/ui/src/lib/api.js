// Substrate API helpers. Single-user, no auth — every fetch hits /api/* directly.
// Project clones extending the substrate add domain endpoints below.

const BASE = '/api'

async function request(method, path, body) {
  const opts = { method, headers: {} }
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(BASE + path, opts)
  if (!res.ok) {
    let detail = `${res.status}`
    try {
      const j = await res.json()
      const d = j.detail ?? detail
      detail = Array.isArray(d) ? d.map(e => e.msg || JSON.stringify(e)).join('; ') : d
    } catch {}
    throw new Error(detail)
  }
  return res.status === 204 ? null : res.json()
}

const get   = (p)    => request('GET',    p)
const post  = (p, b) => request('POST',   p, b ?? {})
const put   = (p, b) => request('PUT',    p, b ?? {})
const patch = (p, b) => request('PATCH',  p, b ?? {})
const del_  = (p, b) => request('DELETE', p, b)

// ── Substrate endpoints ──────────────────────────────────────────────────────

export const getHealth          = ()         => get('/health')
export const getRecentLogs      = ()         => get('/me/recent-logs')
export const searchUsers        = (q = '')   => get(`/users${q ? '?q=' + encodeURIComponent(q) : ''}`)

export const getShells          = ()                   => get('/admin/shells')
export const getShell           = (shell_id)           => get(`/shells/${shell_id}`)
export const getShellSkills     = (shell_id)           => get(`/shells/${shell_id}/skills`)
export const getShellPromptSections = (shell_id)       => get(`/shells/${shell_id}/prompt-sections`)
export const putShellPromptSection  = (shell_id, label, body) =>
  put(`/shells/${shell_id}/prompt-sections/${encodeURIComponent(label)}`, { body })
export const getAvailableSkills = ()                   => get('/admin/skills/available')
export const getSkill           = (skill_id)           => get(`/admin/skills/${skill_id}`)
export const updateSkill        = (skill_id, patch)    => request('PATCH', `/admin/skills/${skill_id}`, patch)
export const addShellSkill      = (shell_id, skill_id) => post(`/admin/shells/${shell_id}/skills`, { skill_id })
export const removeShellSkill   = (shell_id, skill_id) => del_(`/admin/shells/${shell_id}/skills/${skill_id}`)

// ── Browser chat ─────────────────────────────────────────────────────────────

export const getModels             = ()                => get('/models')
export const routeModelToAgents    = (model_id)        => post(`/models/${model_id}/route-to-agents`)
export const getMyShells           = ()                => get('/shells/mine')
export const activateShell         = (shell_id)        => patch(`/shells/${shell_id}/activate`)
export const getShellChat          = (shell_id)        => get(`/shells/${shell_id}/chat`)
export const getShellChatSession   = (shell_id)        => get(`/shells/${shell_id}/chat/session`)
export const createShellChatSession = (shell_id, model_id) =>
  post(`/shells/${shell_id}/chat/session`, model_id != null ? { model_id } : {})
export const postShellChat         = (shell_id, body, chat_session_id) =>
  post(`/shells/${shell_id}/chat`, { body, chat_session_id })
export const clearShellSession     = (shell_id, session_id) =>
  post(`/shells/${shell_id}/sessions/${session_id}/clear`)
export const setSessionModel       = (shell_id, session_id, model_id) =>
  patch(`/shells/${shell_id}/sessions/${session_id}`, { model_id })

export const getFlags           = ()         => get('/flags')
export const searchFlags        = (q)        => get(`/flags/search?q=${encodeURIComponent(q)}`)
export const createFlag         = (body)     => post('/flags', body)
export const updateFlag         = (id, body) => patch(`/flags/${id}`, body)
export const resolveFlag        = (id, status, notes) => patch(`/flags/${id}/resolve`, { status, notes })
export const deleteFlag         = (id)       => del_(`/flags/${id}`)
