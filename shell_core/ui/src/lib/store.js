// Substrate stores — minimal. Project clones extend this.
import { writable } from 'svelte/store'

// Logged-in user (single-user substrate; no auth, but theme/profile lives here).
export const me = writable({ user_id: 1, username: 'Jed' })
