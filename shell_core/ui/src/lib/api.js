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

// ── Auth ──────────────────────────────────────────────────────────────────────
// login is two-step: POST {email, password} returns {stage: 'totp'|'enroll'|
// 'authed'}; resend with {email, password, code} to finish. The session cookie
// is set by the API and relayed through the /api trust seam.
export const login              = (body)     => post('/auth/login', body)
export const logout             = ()         => post('/auth/logout')
export const getMe              = ()         => get('/auth/me')

// ── Admin: user management ─────────────────────────────────────────────────────
// createUser returns the one-time password (shown once for the operator to copy).
export const getAdminUsers      = ()                 => get('/admin/users/full')
export const createUser         = (email, is_admin = 0) => post('/admin/users', { email, is_admin })
export const setUserAdmin       = (user_id, is_admin)   => patch(`/admin/users/${user_id}/admin`, { is_admin })
// rotateUserPassword returns the new one-time password (shown/downloaded once).
export const rotateUserPassword = (user_id)             => post(`/admin/users/${user_id}/rotate-password`)
export const assignShellUser    = (shell_id, user_id)   => patch(`/admin/shells/${shell_id}/assign-user`, { user_id })

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
export const promptRenderUrl        = (shell_id, dialect = 'anthropic') =>
  `${BASE}/shells/${shell_id}/prompt-render?dialect=${encodeURIComponent(dialect)}`
export const getAvailableSkills = ()                   => get('/admin/skills/available')
export const getSkill           = (skill_id)           => get(`/admin/skills/${skill_id}`)
export const updateSkill        = (skill_id, patch)    => request('PATCH', `/admin/skills/${skill_id}`, patch)
export const addShellSkill      = (shell_id, skill_id) => post(`/admin/shells/${shell_id}/skills`, { skill_id })
export const removeShellSkill   = (shell_id, skill_id) => del_(`/admin/shells/${shell_id}/skills/${skill_id}`)
// Rotate a shell's substrate-API key (api_key + api_key_hash + rotated_at).
export const rotateShellKey     = (shell_id)           => post(`/admin/shells/${shell_id}/rotate-key`)

// Tools — general tools (is_general) are universal; the rest are granted per
// shell via shell_tools (and auto-materialised when a requiring skill is
// assigned). getShellTools returns the shell's direct grants with `required_by`.
export const getShellTools      = (shell_id)           => get(`/shells/${shell_id}/tools`)
export const getAvailableTools  = ()                   => get('/admin/tools/available')
export const getTool            = (tool_id)            => get(`/admin/tools/${tool_id}`)
export const addShellTool       = (shell_id, tool_id)  => post(`/admin/shells/${shell_id}/tools`, { tool_id })
export const removeShellTool    = (shell_id, tool_id)  => del_(`/admin/shells/${shell_id}/tools/${tool_id}`)

// ── Browser chat ─────────────────────────────────────────────────────────────

export const getModels             = ()                => get('/models')
export const routeModelToAgents    = (model_id)        => post(`/models/${model_id}/route-to-agents`)

// Ollama Cloud config — list includes inactive rows (the activation surface).
export const getCloudModels        = ()                => get('/models/cloud')
export const setModelStatus        = (model_id, status) =>
  patch(`/models/${model_id}/status`, { status })
export const syncCloudModels       = ()                => post('/models/cloud/sync')

// First-party remote providers (Anthropic, OpenAI) — same surface as cloud,
// one provider per config page. List includes inactive rows.
export const getProviderModels     = (provider)        => get(`/models/remote/${provider}`)
export const syncProviderModels    = (provider)        => post(`/models/remote/${provider}/sync`)

// Keys — secret management via the broker admin API. Values are never returned;
// the list is metadata only (name, last_four, timestamps).
export const getKeys               = ()                => get('/keys')
export const setKey                = (name, value)     => put(`/keys/${encodeURIComponent(name)}`, { value })
export const deleteKey             = (name)            => del_(`/keys/${encodeURIComponent(name)}`)
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
