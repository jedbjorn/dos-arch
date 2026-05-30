<script>
  import { onMount } from 'svelte'
  import { getMe, getAdminUsers, getShells, createUser, setUserAdmin, assignShellUser } from '$lib/api.js'

  let me      = $state(null)
  let users   = $state([])
  let shells  = $state([])
  let loading = $state(true)
  let error   = $state('')
  let denied  = $state(false)

  // create-user form
  let newEmail   = $state('')
  let newAdmin   = $state(false)
  let creating   = $state(false)
  let created    = $state(null)   // {email, password, shell} — one-time password shown here

  async function loadAll() {
    error = ''
    try {
      me = await getMe()
      if (!me.is_admin) { denied = true; return }
      ;[users, shells] = await Promise.all([getAdminUsers(), getShells()])
    } catch (e) {
      error = e.message || 'Failed to load'
    } finally {
      loading = false
    }
  }
  onMount(loadAll)

  async function doCreate(e) {
    e.preventDefault()
    error = ''; creating = true; created = null
    try {
      created = await createUser(newEmail.trim(), newAdmin ? 1 : 0)
      newEmail = ''; newAdmin = false
      ;[users, shells] = await Promise.all([getAdminUsers(), getShells()])
    } catch (e) {
      error = e.message || 'Create failed'
    } finally {
      creating = false
    }
  }

  async function toggleAdmin(u) {
    error = ''
    try {
      await setUserAdmin(u.user_id, u.is_admin ? 0 : 1)
      users = await getAdminUsers()
    } catch (e) {
      error = e.message || 'Update failed'
    }
  }

  async function reassign(shell, user_id) {
    error = ''
    try {
      await assignShellUser(shell.shell_id, user_id === '' ? null : Number(user_id))
      shells = await getShells()
    } catch (e) {
      error = e.message || 'Assign failed'
    }
  }

  async function copyPw() {
    try { await navigator.clipboard.writeText(created.password) } catch {}
  }
</script>

<div class="p-6 max-w-4xl mx-auto w-full text-white/90">
  <h1 class="text-2xl font-semibold mb-6">Admin</h1>

  {#if loading}
    <p class="text-white/50">Loading…</p>
  {:else if denied}
    <p class="text-red-300">Admins only.</p>
  {:else}
    {#if error}
      <div class="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div>
    {/if}

    <!-- Create user -->
    <section class="mb-8 rounded-xl border border-white/10 bg-black/20 p-5">
      <h2 class="text-lg font-medium mb-3">Create user</h2>
      <form onsubmit={doCreate} class="flex flex-wrap items-end gap-3">
        <label class="flex-1 min-w-[220px]">
          <span class="text-xs uppercase tracking-wide text-white/40">Email</span>
          <input bind:value={newEmail} type="email" required placeholder="person@example.com"
            class="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 outline-none focus:border-white/30" />
        </label>
        <label class="flex items-center gap-2 text-sm text-white/70 pb-2">
          <input type="checkbox" bind:checked={newAdmin} /> admin
        </label>
        <button disabled={creating} type="submit"
          class="rounded-lg bg-white/90 text-black font-medium px-4 py-2 hover:bg-white disabled:opacity-50">
          {creating ? '…' : 'Create + mint Exp-NN'}
        </button>
      </form>

      {#if created}
        <div class="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm">
          <p class="text-emerald-200 font-medium mb-1">User created — send these to {created.email}:</p>
          <p class="text-white/70">Assistant minted: <span class="font-mono">{created.shell?.display_name}</span></p>
          <div class="mt-2 flex items-center gap-3">
            <span class="text-white/40 text-xs uppercase">One-time password</span>
            <code class="font-mono text-base select-all bg-black/40 px-2 py-1 rounded">{created.password}</code>
            <button onclick={copyPw} class="text-xs rounded bg-white/10 px-2 py-1 hover:bg-white/20">copy</button>
          </div>
          <p class="text-white/40 text-xs mt-2">Shown once — it is stored only as a hash. They enroll TOTP on first login.</p>
        </div>
      {/if}
    </section>

    <!-- Users -->
    <section class="mb-8">
      <h2 class="text-lg font-medium mb-3">Users</h2>
      <table class="w-full text-sm">
        <thead class="text-white/40 text-xs uppercase">
          <tr class="text-left border-b border-white/10">
            <th class="py-2">Email</th><th>Admin</th><th>TOTP</th><th>Shells</th><th>Status</th>
          </tr>
        </thead>
        <tbody>
          {#each users as u (u.user_id)}
            <tr class="border-b border-white/5">
              <td class="py-2">{u.email || u.username}</td>
              <td>
                <button onclick={() => toggleAdmin(u)}
                  class="rounded px-2 py-0.5 text-xs {u.is_admin ? 'bg-amber-500/20 text-amber-300' : 'bg-white/10 text-white/50'} hover:opacity-80">
                  {u.is_admin ? 'admin' : 'user'}
                </button>
              </td>
              <td>{u.totp_enrolled ? '✓' : '—'}</td>
              <td>{u.shell_count}</td>
              <td class="text-white/50">{u.is_active ? 'active' : 'disabled'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>

    <!-- Shell assignment -->
    <section>
      <h2 class="text-lg font-medium mb-3">Shells</h2>
      <table class="w-full text-sm">
        <thead class="text-white/40 text-xs uppercase">
          <tr class="text-left border-b border-white/10"><th class="py-2">Shell</th><th>Owner</th></tr>
        </thead>
        <tbody>
          {#each shells as s (s.shell_id)}
            <tr class="border-b border-white/5">
              <td class="py-2">{s.display_name} <span class="text-white/30 text-xs">#{s.shell_id}</span></td>
              <td>
                <select value={s.user_id ?? ''} onchange={(e) => reassign(s, e.currentTarget.value)}
                  class="rounded-lg bg-white/5 border border-white/10 px-2 py-1 outline-none focus:border-white/30">
                  <option value="">— unassigned —</option>
                  {#each users as u (u.user_id)}
                    <option value={u.user_id}>{u.email || u.username}</option>
                  {/each}
                </select>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {/if}
</div>
