<script>
  // Right-side user drawer — the mirror of SideDrawer. Left drawer = app mode
  // (surfaces, config); right drawer = the current user (account, session).
  // Stub for now: identity readout + Sign out. User-specific controls land here.
  import { logout } from '$lib/api.js'

  let { open = $bindable(false), me = null } = $props()

  let busy = $state(false)

  function close() { open = false }

  async function signOut() {
    busy = true
    try {
      await logout()              // revokes the session row + clears the cookie
    } catch { /* sign out is best-effort; redirect regardless */ }
    // Full navigation so hooks.server.js re-evaluates (now no session) and the
    // app state is dropped.
    window.location.href = '/login'
  }
</script>

{#if open}
  <div class="fixed inset-0 z-40 pointer-events-none">
    <aside
      class="absolute right-0 top-0 bottom-0 w-72 pointer-events-auto flex flex-col border-l border-white/[0.08]"
      style="background: rgba(20, 20, 25, 0.95);"
      onmouseleave={close}
    >
      <div class="px-5 py-4 border-b border-white/[0.08]">
        <div class="text-[10px] tracking-[0.25em] uppercase text-white/40">Account</div>
      </div>

      <div class="flex-1 overflow-y-auto py-2">
        <div class="px-5 py-3">
          <div class="text-[13px] text-white/85 truncate">{me?.email ?? '—'}</div>
          {#if me?.is_admin}
            <span class="mt-1 inline-block rounded px-2 py-0.5 text-[10px] uppercase tracking-wider bg-amber-500/20 text-amber-300">admin</span>
          {/if}
        </div>
      </div>

      <div class="px-5 py-4 border-t border-white/[0.08]">
        <button
          type="button"
          onclick={signOut}
          disabled={busy}
          class="w-full rounded-lg border border-white/10 bg-white/[0.04] px-4 py-2.5 text-[13px] text-white/80 hover:text-white hover:bg-white/[0.08] disabled:opacity-50 transition"
        >
          {busy ? 'Signing out…' : 'Sign out'}
        </button>
      </div>
    </aside>
  </div>
{/if}
