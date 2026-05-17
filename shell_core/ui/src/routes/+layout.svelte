<script>
  import '../routes/layout.css'
  import { onMount } from 'svelte'
  import { theme, applyTheme, loadThemeFromApi } from '$lib/theme.js'
  import TopBar from '$lib/components/TopBar.svelte'

  onMount(() => {
    const t = $theme
    applyTheme(t.bg, t.accent)
    loadThemeFromApi()
  })

  let { children } = $props()
</script>

<div class="min-h-screen bg-surface-1 text-text font-mono">
  <div class="max-w-[1250px] mx-auto w-full">
    <TopBar />
    <main class="flex flex-col min-h-[calc(100vh-52px)]">
      {@render children()}
    </main>
  </div>
</div>
