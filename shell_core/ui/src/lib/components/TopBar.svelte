<script>
  // App header — route tabs sit on a translucent glass strip; active tab
  // gets a 2px accent underline via the shared .active-tab class.
  import { onMount } from 'svelte'
  import { page } from '$app/stores'
  import { goto } from '$app/navigation'
  import { getMe } from '$lib/api.js'
  import SideDrawer from './SideDrawer.svelte'
  import RightDrawer from './RightDrawer.svelte'

  const TABS = [
    { label: 'Workspace', href: '/workspace' },
    { label: 'Projects',  href: '/projects'  },
    { label: 'Flags',     href: '/flags'     },
    { label: 'Emails',    href: '/emails'    },
    { label: 'Contacts',  href: '/contacts'  },
    { label: 'Calendar',  href: '/calendar'  },
  ]

  function isActive(href) { return $page.url.pathname.startsWith(href) }

  let drawerOpen     = $state(false)   // left: app mode
  let userDrawerOpen = $state(false)   // right: user/account

  // Loaded once here and passed to both drawers (single /auth/me, no flicker).
  let me = $state(null)
  onMount(async () => { try { me = await getMe() } catch {} })
  const userInitials = $derived(me?.email ? me.email[0].toUpperCase() : '—')
</script>

<header
  class="h-[52px] sticky top-0 z-30 flex items-center px-5 border-b border-white/[0.08]"
  style="background: rgba(255, 255, 255, 0.02);"
>
  <button
    onclick={() => (drawerOpen = true)}
    aria-label="Open menu"
    class="text-white/60 hover:text-white/90 mr-3 p-1 transition"
  >
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round">
      <line x1="3" y1="5" x2="13" y2="5" />
      <line x1="3" y1="8" x2="13" y2="8" />
      <line x1="3" y1="11" x2="13" y2="11" />
    </svg>
  </button>
  <span class="text-sm font-medium text-white tracking-tight mr-6">shell-infra</span>
  <nav class="flex items-center gap-1">
    {#each TABS as tab}
      {@const active = isActive(tab.href)}
      <button
        onclick={() => goto(tab.href)}
        class="px-3 py-2 text-sm transition whitespace-nowrap
               {active
                  ? 'active-tab'
                  : 'text-white/60 hover:text-white/90'}"
      >
        {tab.label}
      </button>
    {/each}
  </nav>

  <!-- Avatar — opens the right (user/account) drawer, mirror of the left. -->
  <button
    type="button"
    onclick={() => (userDrawerOpen = true)}
    aria-label="Account"
    title="Account"
    class="ml-auto w-8 h-8 rounded-full border border-white/[0.10] flex items-center justify-center text-[11px] font-medium text-white/70 hover:text-white hover:border-white/20 transition"
  >
    {userInitials}
  </button>
</header>

<SideDrawer bind:open={drawerOpen} {me} />
<RightDrawer bind:open={userDrawerOpen} {me} />
