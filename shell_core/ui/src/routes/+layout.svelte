<script>
  import '../routes/layout.css'
  import { onMount } from 'svelte'
  import { theme, applyTheme, loadThemeFromApi } from '$lib/theme.js'
  import TopBar from '$lib/components/TopBar.svelte'
  import ChatSidebar from '$lib/components/ChatSidebar.svelte'

  onMount(() => {
    const t = $theme
    applyTheme(t.bg, t.accent)
    loadThemeFromApi()
  })

  let { children } = $props()
</script>

<!-- Split shell: page content on the left, the chat sidebar docked right.
     dos-arch is a chat-first interface — the sidebar is always present. -->
<div class="flex h-screen overflow-hidden bg-surface-1 text-text font-mono">
  <div class="flex-1 overflow-y-auto">
    <div class="max-w-[1250px] mx-auto w-full">
      <TopBar />
      <main class="flex flex-col min-h-[calc(100vh-52px)]">
        {@render children()}
      </main>
    </div>
  </div>
  <ChatSidebar />
</div>
