import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// The UI calls the substrate API as same-origin `/api/*` (see lib/api.js).
// As of the auth spine that `/api/*` is served by a real SvelteKit server route
// (routes/api/[...path]/+server.js — the trust seam), NOT a Vite dev proxy: the
// seam injects the session cookie + INTERNAL_PROXY_SECRET so the API can tell a
// proxied user request from a direct hit. The dev proxy is removed — it would
// shadow the server route.
export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
});
