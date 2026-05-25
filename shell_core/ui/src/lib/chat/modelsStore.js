// Shared models registry — the chat sidebar's model picker reads it and
// `/ollamacloudconfig` triggers a refresh whenever it activates/deactivates
// or re-syncs the catalog. The sidebar lives in the root layout (chat-first
// UX, persistent across routes), so without this store its initial fetch
// would be the only fetch for the page's lifetime.
import { writable } from 'svelte/store'
import { getModels } from '$lib/api.js'

export const chatModels = writable([])

export async function refreshModels() {
  try {
    chatModels.set(await getModels())
  } catch {
    // Swallow — caller surfaces its own error state; a failed refresh
    // leaves the last-known list in place rather than blanking it.
  }
}
