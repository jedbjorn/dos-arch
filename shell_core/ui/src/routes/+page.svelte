<script>
  // Root route — redirects to /shells on mount. The landing surface for
  // the substrate UI is the shells viewer; no neutral home page.
  import { goto } from '$app/navigation'
  import { onMount } from 'svelte'
  onMount(() => goto('/shells', { replaceState: true }))
</script>
