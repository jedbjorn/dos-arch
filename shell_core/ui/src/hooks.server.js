// Page-load auth gate. A lightweight /auth/me check (via the API, with the
// request's cookie + internal secret) decides whether a *page navigation* is
// allowed. Unauthenticated HTML navigations are redirected to /login. This owns
// only redirect UX — the API remains the real authority on every data request.
//
// Deliberately narrow: only top-level HTML navigations are gated. `/api/*` (the
// trust seam) and `/login` pass through, and non-HTML requests (JS, assets,
// data) are never redirected — a redirected asset would break the page.
import { redirect } from '@sveltejs/kit';

const API = process.env.API_TARGET || 'http://127.0.0.1:8001';
const SECRET = process.env.INTERNAL_PROXY_SECRET || '';

async function isAuthed(event) {
  try {
    const res = await fetch(`${API}/auth/me`, {
      headers: {
        cookie: event.request.headers.get('cookie') || '',
        'x-internal-auth': SECRET,
      },
    });
    return res.ok;
  } catch {
    return false; // API down → treat as unauthenticated (fail closed)
  }
}

/** @type {import('@sveltejs/kit').Handle} */
export async function handle({ event, resolve }) {
  const { pathname } = event.url;

  // The seam and the login page are never gated.
  if (pathname.startsWith('/api') || pathname === '/login') {
    return resolve(event);
  }

  // Only gate real page navigations (HTML), so assets/data still load.
  const wantsHtml = (event.request.headers.get('accept') || '').includes('text/html');
  if (wantsHtml && !(await isAuthed(event))) {
    throw redirect(303, '/login');
  }

  return resolve(event);
}
