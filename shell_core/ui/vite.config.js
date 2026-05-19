import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// The UI calls the substrate API as same-origin `/api/*` (see lib/api.js).
// In dev the SvelteKit server proxies that to the API process, stripping the
// `/api` prefix — the API routers carry no prefix (e.g. /shells/mine).
// API_TARGET overrides the default for non-standard local layouts.
const API_TARGET = process.env.API_TARGET || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  server: {
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
