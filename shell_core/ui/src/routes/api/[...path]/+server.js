// Trust seam — the only path from the browser to the substrate API.
//
// Every `/api/*` request hits this server route (it replaced the Vite dev
// proxy). It forwards to the loopback API stripping the `/api` prefix, and adds
// the INTERNAL_PROXY_SECRET header so the API knows the request came through the
// proxy (a user-surface request) rather than a direct local hit. The session
// cookie rides along; the API resolves the user from it. Set-Cookie from the
// API (login/logout) is relayed back to the browser verbatim.
//
// The browser never holds the internal secret — only this server process does.

const API = process.env.API_TARGET || 'http://127.0.0.1:8001';
const SECRET = process.env.INTERNAL_PROXY_SECRET || '';

// Headers we must not forward verbatim (host/length recomputed by fetch).
const STRIP_REQ = new Set(['host', 'connection', 'content-length']);
const STRIP_RES = new Set(['content-encoding', 'content-length', 'transfer-encoding', 'connection']);

/** @type {import('./$types').RequestHandler} */
export async function fallback({ request, params, url }) {
  const target = `${API}/${params.path}${url.search}`;

  const headers = new Headers();
  for (const [k, v] of request.headers) {
    if (!STRIP_REQ.has(k.toLowerCase())) headers.set(k, v);
  }
  headers.set('x-internal-auth', SECRET);

  const init = { method: request.method, headers, redirect: 'manual' };
  if (!['GET', 'HEAD'].includes(request.method)) {
    init.body = await request.arrayBuffer();
  }

  let res;
  try {
    res = await fetch(target, init);
  } catch {
    return new Response(JSON.stringify({ detail: 'API unreachable' }), {
      status: 502, headers: { 'content-type': 'application/json' },
    });
  }

  // Relay status + headers, preserving every Set-Cookie line (getSetCookie
  // keeps them un-folded — a plain Headers copy can merge them).
  const out = new Headers();
  for (const [k, v] of res.headers) {
    if (k.toLowerCase() !== 'set-cookie' && !STRIP_RES.has(k.toLowerCase())) out.set(k, v);
  }
  const cookies = res.headers.getSetCookie?.() ?? [];
  for (const c of cookies) out.append('set-cookie', c);

  return new Response(res.body, { status: res.status, headers: out });
}
