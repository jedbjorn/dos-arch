<script>
  // Root route — redirects to /workspace on mount. Workspace is the
  // landing surface for the substrate UI; no neutral home page.
  import { goto } from '$app/navigation'
  import { onMount } from 'svelte'
  onMount(() => goto('/workspace', { replaceState: true }))
</script>
