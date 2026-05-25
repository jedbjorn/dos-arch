// Model registry helpers for the chat sidebar.

export const PROVIDERS = [
  { key: 'anthropic',    label: 'Anthropic' },
  { key: 'openai',       label: 'OpenAI' },
  { key: 'ollama_cloud', label: 'Ollama Cloud' },
  { key: 'local',        label: 'Local' },
]

// Per-provider header rows carry redundant "(local)" / "(cloud)" suffixes
// on display_name from the DB; strip them in the list.
export const modelLabel = (m) =>
  (m?.display_name ?? '').replace(/\s*\((local|cloud)\)\s*$/i, '')

export const modelsByProvider = (models) =>
  Object.fromEntries(PROVIDERS.map(p => [p.key, models.filter(m => m.provider === p.key)]))

export const defaultModelId = (models) => {
  const def = models.find(m => m.name === 'claude-sonnet-4-6') ?? models[0]
  return def ? def.model_id : null
}
