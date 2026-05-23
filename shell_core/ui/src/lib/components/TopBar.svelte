<script>
  // App header — route tabs sit on a translucent glass strip; active tab
  // gets the accent gradient via the shared .active-pill class.
  import { page } from '$app/stores'
  import { goto } from '$app/navigation'

  const TABS = [
    { label: 'Shells', href: '/shells' },
    { label: 'Flags',  href: '/flags'  },
    { label: 'Plans',  href: '/plans'  },
  ]

  function isActive(href) { return $page.url.pathname.startsWith(href) }
</script>

<header
  class="h-[52px] sticky top-0 z-30 flex items-center px-5 border-b border-white/[0.08]"
  style="background: rgba(255, 255, 255, 0.02);
         backdrop-filter: blur(24px);
         -webkit-backdrop-filter: blur(24px);"
>
  <span class="text-sm font-medium text-white tracking-tight mr-6">shell-infra</span>
  <nav class="flex items-center gap-1">
    {#each TABS as tab}
      {@const active = isActive(tab.href)}
      <button
        onclick={() => goto(tab.href)}
        class="px-3 py-2 rounded-xl text-sm transition whitespace-nowrap
               {active
                  ? 'active-pill'
                  : 'text-white/60 hover:text-white/90 hover:bg-white/[0.03]'}"
      >
        {tab.label}
      </button>
    {/each}
  </nav>
</header>
