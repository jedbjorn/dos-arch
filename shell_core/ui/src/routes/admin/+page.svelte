<script>
  import { onMount } from 'svelte'
  import { getMe, getAdminUsers, getShells, createUser, setUserAdmin, resetUserAuth, assignShellUser } from '$lib/api.js'
  import GlassDropdown from '$lib/components/GlassDropdown.svelte'
  import Switch from '$lib/components/Switch.svelte'

  let me      = $state(null)
  let users   = $state([])
  let shells  = $state([])
  let loading = $state(true)
  let error   = $state('')
  let denied  = $state(false)

  // create-user modal
  let showCreate = $state(false)
  let newEmail   = $state('')
  let newAdmin   = $state(false)
  let creating   = $state(false)
  let created    = $state(null)   // {email, password, shell} — one-time password shown here

  // Modal escapes any ancestor stacking context to paint above siblings.
  function portal(node) {
    document.body.appendChild(node)
    return { destroy() { node.parentNode?.removeChild(node) } }
  }

  function openCreate() {
    created = null; error = ''; newEmail = ''; newAdmin = false
    showCreate = true
  }
  function closeCreate() {
    showCreate = false; created = null; error = ''; newEmail = ''; newAdmin = false
  }

  // edit-user modal — email/name/initials read-only; is_admin editable; rotate pw
  let editUser  = $state(null)   // a copy of the row being edited
  let resetting = $state(false)
  let resetPw   = $state(null)   // the freshly-minted one-time password

  function openEdit(u) {
    editUser = { ...u }; resetPw = null; error = ''
  }
  function closeEdit() {
    editUser = null; resetPw = null; error = ''
  }

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

  async function toggleEditAdmin(v) {
    if (!editUser) return
    error = ''
    const prev = editUser.is_admin
    editUser.is_admin = v ? 1 : 0   // optimistic
    try {
      await setUserAdmin(editUser.user_id, v ? 1 : 0)
      users = await getAdminUsers()
    } catch (e) {
      error = e.message || 'Update failed'
      editUser.is_admin = prev       // revert on failure (e.g. last-admin guard)
    }
  }

  async function doResetAuth() {
    if (!editUser) return
    error = ''; resetting = true; resetPw = null
    try {
      const res = await resetUserAuth(editUser.user_id)
      resetPw = res.password
      downloadCreds(res.email, res.password)
      // TOTP was cleared server-side — reflect it in the open modal + the table.
      editUser.totp_enrolled = 0
      users = await getAdminUsers()
    } catch (e) {
      error = e.message || 'Reset failed'
    } finally {
      resetting = false
    }
  }

  // Download a plaintext credential handoff. The password is shown only once;
  // the .txt is the operator's copy to send to the user.
  function downloadCreds(email, password) {
    const body = `email:    ${email}\npassword: ${password}\n`
    const blob = new Blob([body], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${email}-password.txt`
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
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

    <!-- Users -->
    <section class="mb-8">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-medium">Users</h2>
        <button type="button" onclick={openCreate}
          class="px-3 py-1.5 rounded-full text-xs font-medium border border-white/20 text-white hover:bg-white/[0.06] transition">
          + User
        </button>
      </div>
      <table class="w-full text-sm">
        <thead class="text-white/40 text-xs uppercase">
          <tr class="text-left border-b border-white/10">
            <th class="py-2">Email</th><th>Admin</th><th>TOTP</th><th>Shells</th><th>Status</th><th></th>
          </tr>
        </thead>
        <tbody>
          {#each users as u (u.user_id)}
            <tr class="border-b border-white/5">
              <td class="py-2">{u.email || u.username}</td>
              <td>
                <span class="rounded px-2 py-0.5 text-xs {u.is_admin ? 'bg-amber-500/20 text-amber-300' : 'bg-white/10 text-white/50'}">
                  {u.is_admin ? 'admin' : 'user'}
                </span>
              </td>
              <td>{u.totp_enrolled ? '✓' : '—'}</td>
              <td>{u.shell_count}</td>
              <td class="text-white/50">{u.is_active ? 'active' : 'disabled'}</td>
              <td class="text-right">
                <button type="button" onclick={() => openEdit(u)}
                  class="text-xs text-white/50 hover:text-white border border-white/[0.10] hover:border-white/20 rounded px-2 py-0.5 transition">
                  Edit
                </button>
              </td>
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
                <GlassDropdown
                  value={s.user_id ?? ''}
                  items={[
                    { value: '', label: '— unassigned —' },
                    ...users.map((u) => ({ value: u.user_id, label: u.email || u.username })),
                  ]}
                  onChange={(v) => reassign(s, v)}
                />
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {/if}
</div>

<!-- Create-user modal — standard dialog: portal'd overlay, centered card on
     --menu-bg, primary action bottom-left / Cancel bottom-right. After create,
     the form is replaced by the one-time-password panel + a Done button. -->
{#if showCreate}
  <div
    use:portal
    class="fixed inset-0 z-50 flex items-center justify-center"
    style="background: rgba(0,0,0,0.55);"
    onmousedown={closeCreate}
    role="presentation"
  >
    <div
      class="flex flex-col rounded-2xl border border-white/[0.10] shadow-2xl w-[440px] max-w-[90vw]"
      style="background: var(--menu-bg);"
      onmousedown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      aria-label="Create user"
      tabindex="-1"
    >
      <div class="flex items-center px-5 pt-4 pb-3 border-b border-white/[0.08]">
        <div class="text-sm font-medium text-white/90">Create user</div>
      </div>

      {#if created}
        <div class="p-5">
          <div class="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm">
            <p class="text-emerald-200 font-medium mb-1">User created — send these to {created.email}:</p>
            <p class="text-white/70">Assistant minted: <span class="font-mono">{created.shell?.display_name}</span></p>
            <div class="mt-2 flex items-center gap-3">
              <span class="text-white/40 text-xs uppercase">One-time password</span>
              <code class="font-mono text-base select-all bg-black/40 px-2 py-1 rounded">{created.password}</code>
              <button onclick={copyPw} class="text-xs rounded bg-white/10 px-2 py-1 hover:bg-white/20">copy</button>
            </div>
            <p class="text-white/40 text-xs mt-2">Shown once — it is stored only as a hash. They enroll TOTP on first login.</p>
          </div>
        </div>
        <div class="flex items-center justify-end px-5 pb-4 pt-2 border-t border-white/[0.08]">
          <button type="button" onclick={closeCreate}
            class="px-4 py-1.5 rounded-full text-xs font-medium border border-white/20 text-white hover:bg-white/[0.06] transition">Done</button>
        </div>
      {:else}
        <form onsubmit={doCreate} class="contents">
          <div class="p-5 flex flex-col gap-4">
            {#if error}
              <div class="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div>
            {/if}
            <label class="block">
              <span class="text-xs uppercase tracking-wide text-white/40">Email</span>
              <!-- svelte-ignore a11y_autofocus -->
              <input bind:value={newEmail} type="email" required autofocus placeholder="person@example.com"
                class="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 outline-none focus:border-white/30" />
            </label>
            <div class="flex items-center gap-3">
              <Switch checked={newAdmin} onChange={(v) => (newAdmin = v)} label="admin" />
              <span class="text-sm text-white/70">Admin</span>
            </div>
          </div>
          <div class="flex items-center justify-between px-5 pb-4 pt-2 border-t border-white/[0.08]">
            <button type="submit" disabled={creating}
              class="px-4 py-1.5 rounded-full text-xs font-medium border border-white/20 text-white hover:bg-white/[0.06] transition disabled:opacity-40">
              {creating ? 'Creating…' : 'Create'}
            </button>
            <button type="button" onclick={closeCreate} disabled={creating}
              class="px-4 py-1.5 rounded-full text-xs text-white/70 hover:text-white border border-white/[0.10] hover:border-white/20 transition disabled:opacity-40">
              Cancel
            </button>
          </div>
        </form>
      {/if}
    </div>
  </div>
{/if}

<!-- Edit-user modal — email/name/initials read-only; is_admin via Switch
     (persists on toggle); Reset User Auth mints a new one-time password AND
     resets TOTP (locked-out-user recovery), downloading the password as a
     .txt for handoff. -->
{#if editUser}
  <div
    use:portal
    class="fixed inset-0 z-50 flex items-center justify-center"
    style="background: rgba(0,0,0,0.55);"
    onmousedown={closeEdit}
    role="presentation"
  >
    <div
      class="flex flex-col rounded-2xl border border-white/[0.10] shadow-2xl w-[440px] max-w-[90vw]"
      style="background: var(--menu-bg);"
      onmousedown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      aria-label="Edit user"
      tabindex="-1"
    >
      <div class="flex items-center px-5 pt-4 pb-3 border-b border-white/[0.08]">
        <div class="text-sm font-medium text-white/90">Edit user</div>
      </div>

      <div class="p-5 flex flex-col gap-4">
        {#if error}
          <div class="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div>
        {/if}

        <!-- Read-only identity. -->
        <div class="grid grid-cols-[88px_1fr] gap-x-3 gap-y-2 text-sm items-center">
          <span class="text-xs uppercase tracking-wide text-white/40">Email</span>
          <span class="text-white/80 truncate">{editUser.email || '—'}</span>
          <span class="text-xs uppercase tracking-wide text-white/40">Name</span>
          <span class="text-white/80 truncate">{editUser.username || '—'}</span>
          <span class="text-xs uppercase tracking-wide text-white/40">Initials</span>
          <span class="text-white/80">{editUser.initials || '—'}</span>
        </div>

        <!-- Admin — persists immediately on toggle. -->
        <div class="flex items-center gap-3 pt-1">
          <Switch checked={!!editUser.is_admin} onChange={toggleEditAdmin} label="admin" />
          <span class="text-sm text-white/70">Admin</span>
        </div>

        <!-- Auth recovery — rotates password + resets TOTP together. -->
        <div class="border-t border-white/[0.08] pt-4">
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0">
              <div class="text-sm text-white/80">Authentication</div>
              <div class="text-xs text-white/40">Mint a new one-time password and reset TOTP for a locked-out user.</div>
            </div>
            <button type="button" onclick={doResetAuth} disabled={resetting}
              class="shrink-0 px-3 py-1.5 rounded-full text-xs font-medium border border-white/20 text-white hover:bg-white/[0.06] transition disabled:opacity-40">
              {resetting ? 'Resetting…' : 'Reset User Auth'}
            </button>
          </div>
          {#if resetPw}
            <div class="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">
              <p class="text-emerald-200 font-medium mb-1">Auth reset — password downloaded as {editUser.email}-password.txt</p>
              <div class="flex items-center gap-3">
                <code class="font-mono text-base select-all bg-black/40 px-2 py-1 rounded">{resetPw}</code>
                <button onclick={() => navigator.clipboard.writeText(resetPw)}
                  class="text-xs rounded bg-white/10 px-2 py-1 hover:bg-white/20">copy</button>
              </div>
              <p class="text-white/40 text-xs mt-2">Shown once — stored only as a hash. TOTP was cleared; the user re-enrolls on next login.</p>
            </div>
          {/if}
        </div>
      </div>

      <div class="flex items-center justify-end px-5 pb-4 pt-2 border-t border-white/[0.08]">
        <button type="button" onclick={closeEdit}
          class="px-4 py-1.5 rounded-full text-xs text-white/70 hover:text-white border border-white/[0.10] hover:border-white/20 transition">
          Done
        </button>
      </div>
    </div>
  </div>
{/if}
