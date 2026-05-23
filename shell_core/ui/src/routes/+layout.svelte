<script>
  import '../routes/layout.css'
  import { onMount } from 'svelte'
  import { theme, applyTheme, loadThemeFromApi } from '$lib/theme.js'
  import TopBar from '$lib/components/TopBar.svelte'
  import ChatSidebar from '$lib/components/chat/ChatSidebar.svelte'

  onMount(() => {
    applyTheme($theme)
    loadThemeFromApi()
  })

  let { children } = $props()

  // Inline SVG noise — tiny, no extra request. Layered as a faint overlay
  // to break up the smooth gradient washes; mix-blend-overlay keeps it
  // visible against any background.
  const GRAIN_URL =
    "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")"
</script>

<!-- Split shell: page content on the left, the chat sidebar docked right.
     dos-arch is a chat-first interface — the sidebar is always present.
     Background gradient + grain live on body via layout.css; this root
     stays transparent so the canvas shows through. -->
<div class="flex h-screen overflow-hidden relative">
  <!-- Grain overlay — fixed so it stays put while panels scroll. -->
  <div
    class="fixed inset-0 opacity-[0.05] pointer-events-none mix-blend-overlay z-0"
    style="background-image: {GRAIN_URL};"
  ></div>

  <div class="flex-1 overflow-y-auto relative z-10">
    <div class="max-w-[1250px] mx-auto w-full">
      <TopBar />
      <main class="flex flex-col min-h-[calc(100vh-52px)]">
        {@render children()}
      </main>
    </div>
  </div>
  <ChatSidebar />
</div>
