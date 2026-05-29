// Shared API-keys metadata store. The Keys page (/keysconfig) writes to it on
// load / save / delete; the provider config pages read it to gate their model
// lists on whether that provider's key is present, and to react live when a
// key is added, rotated, or removed — no page reload. Metadata only (name,
// last_four, last_rotated_at); secret values are never read back from the
// broker, so they never enter this store.
import { writable } from 'svelte/store'
import { getKeys } from '$lib/api.js'

export const apiKeys = writable([])

export async function refreshKeys() {
  try {
    apiKeys.set(await getKeys())
  } catch {
    // Swallow — a failed refresh leaves the last-known list in place rather
    // than blanking it. The Keys page surfaces its own error state.
  }
}
