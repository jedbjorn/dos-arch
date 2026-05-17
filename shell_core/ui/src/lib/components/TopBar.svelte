<script>
  import { page } from '$app/stores'
  import { goto } from '$app/navigation'

  const TABS = [
    { label: 'Shells', href: '/shells' },
    { label: 'Flags',  href: '/flags'  },
    { label: 'Plans',  href: '/plans'  },
  ]

  function isActive(href) { return $page.url.pathname.startsWith(href) }
</script>

<header class="h-[52px] sticky top-0 z-30 flex items-center px-5
               bg-surface-1 border-b border-border">
  <span class="text-sm font-medium text-text tracking-tight mr-6">shell-infra</span>
  <nav class="flex items-center h-[52px]">
    {#each TABS as tab}
      <button
        onclick={() => goto(tab.href)}
        class="h-full px-4 text-[13px] border-b-2 transition-all whitespace-nowrap
               {isActive(tab.href)
                 ? 'border-accent text-text font-medium'
                 : 'border-transparent text-text-dim hover:text-text'}"
      >
        {tab.label}
      </button>
    {/each}
  </nav>
</header>
