// Model registry helpers for the chat sidebar.

export const PROVIDERS = [
  { key: 'anthropic', label: 'Anthropic' },
  { key: 'openai',    label: 'OpenAI' },
  { key: 'local',     label: 'Local' },
]

// Local rows sit under the "Local" header — the "(local)" suffix the DB
// carries on their display_name is redundant in the list.
export const modelLabel = (m) =>
  (m?.display_name ?? '').replace(/\s*\(local\)\s*$/i, '')

export const modelsByProvider = (models) =>
  Object.fromEntries(PROVIDERS.map(p => [p.key, models.filter(m => m.provider === p.key)]))

export const defaultModelId = (models) => {
  const def = models.find(m => m.name === 'claude-sonnet-4-6') ?? models[0]
  return def ? def.model_id : null
}
