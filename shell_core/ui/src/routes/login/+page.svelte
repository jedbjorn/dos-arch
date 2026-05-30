<script>
  import { login } from '$lib/api.js'
  import QRCode from 'qrcode'

  // creds → (totp | enroll) → authed. The flow is stateless: we re-send email +
  // password together with the code, so there is no server-side pre-auth state.
  let stage   = $state('creds')   // 'creds' | 'totp' | 'enroll'
  let email   = $state('')
  let password = $state('')
  let code    = $state('')
  let secret  = $state('')        // base32, shown for manual authenticator entry
  let qr      = $state('')        // data-URL QR of the otpauth:// URI
  let error   = $state('')
  let busy    = $state(false)

  async function submitCreds(e) {
    e.preventDefault()
    error = ''; busy = true
    try {
      const r = await login({ email, password })
      if (r.stage === 'authed')      return finish()
      if (r.stage === 'totp')        stage = 'totp'
      else if (r.stage === 'enroll') {
        secret = r.secret
        qr = await QRCode.toDataURL(r.otpauth_uri, { margin: 1, width: 200 })
        stage = 'enroll'
      }
    } catch (err) {
      error = err.message || 'Login failed'
    } finally {
      busy = false
    }
  }

  async function submitCode(e) {
    e.preventDefault()
    error = ''; busy = true
    try {
      const r = await login({ email, password, code })
      if (r.stage === 'authed') return finish()
      error = 'Unexpected response'
    } catch (err) {
      error = err.message || 'Invalid code'
      code = ''
    } finally {
      busy = false
    }
  }

  function finish() {
    // Full reload so hooks.server.js re-evaluates the now-authenticated session.
    window.location.href = '/'
  }
</script>

<div class="min-h-screen flex items-center justify-center p-6">
  <div class="w-full max-w-sm rounded-2xl border border-white/10 bg-black/30 backdrop-blur p-8 shadow-xl">
    <h1 class="text-xl font-semibold text-white/90 mb-1">dos-arch</h1>
    <p class="text-sm text-white/50 mb-6">
      {#if stage === 'creds'}Sign in to continue
      {:else if stage === 'totp'}Enter your authenticator code
      {:else}Set up two-factor authentication{/if}
    </p>

    {#if error}
      <div class="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
        {error}
      </div>
    {/if}

    {#if stage === 'creds'}
      <form onsubmit={submitCreds} class="space-y-4">
        <label class="block">
          <span class="text-xs uppercase tracking-wide text-white/40">Email</span>
          <input bind:value={email} type="email" autocomplete="username" required
            class="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-white/90 outline-none focus:border-white/30" />
        </label>
        <label class="block">
          <span class="text-xs uppercase tracking-wide text-white/40">Password</span>
          <input bind:value={password} type="password" autocomplete="current-password" required
            class="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-white/90 outline-none focus:border-white/30" />
        </label>
        <button disabled={busy} type="submit"
          class="w-full rounded-lg bg-white/90 text-black font-medium py-2 hover:bg-white disabled:opacity-50">
          {busy ? '…' : 'Continue'}
        </button>
      </form>
    {:else}
      <form onsubmit={submitCode} class="space-y-4">
        {#if stage === 'enroll'}
          <p class="text-sm text-white/60">
            Scan this with your authenticator app (or enter the key manually), then enter the 6-digit code.
          </p>
          {#if qr}
            <img src={qr} alt="TOTP QR code" class="mx-auto rounded-lg bg-white p-2" width="200" height="200" />
          {/if}
          <code class="block text-center text-xs tracking-widest text-white/50 break-all select-all">{secret}</code>
        {/if}
        <label class="block">
          <span class="text-xs uppercase tracking-wide text-white/40">6-digit code</span>
          <input bind:value={code} inputmode="numeric" pattern="[0-9]*" maxlength="6" autocomplete="one-time-code" required
            class="mt-1 w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-center text-lg tracking-[0.4em] text-white/90 outline-none focus:border-white/30" />
        </label>
        <button disabled={busy} type="submit"
          class="w-full rounded-lg bg-white/90 text-black font-medium py-2 hover:bg-white disabled:opacity-50">
          {busy ? '…' : (stage === 'enroll' ? 'Verify & enable' : 'Sign in')}
        </button>
      </form>
    {/if}
  </div>
</div>
