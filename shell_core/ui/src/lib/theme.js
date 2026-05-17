// Theme handling — persistent bg/accent presets in localStorage.
import { writable } from 'svelte/store'

const STORAGE_KEY = 'dos_theme'

export const BG_PRESETS     = ['#0f1117', '#0f172a', '#1c1412', '#0d1f17', '#1a0a0e', '#170f2e']
export const ACCENT_PRESETS = ['#0072FF', '#3b82f6', '#d97706', '#10b981', '#e11d48', '#8b5cf6']

function lighten(hex, amt) {
  const r = Math.min(255, parseInt(hex.slice(1,3),16) + Math.round(255*amt))
  const g = Math.min(255, parseInt(hex.slice(3,5),16) + Math.round(255*amt))
  const b = Math.min(255, parseInt(hex.slice(5,7),16) + Math.round(255*amt))
  return '#' + [r,g,b].map(v => v.toString(16).padStart(2,'0')).join('')
}

export function applyTheme(bg, accent) {
  if (typeof document === 'undefined') return
  let el = document.getElementById('dos-theme')
  if (!el) {
    el = document.createElement('style')
    el.id = 'dos-theme'
    document.head.appendChild(el)
  }
  el.textContent = `
    :root, html, body {
      --color-surface-1: ${bg};
      --color-surface-2: ${lighten(bg, 0.04)};
      --color-surface-3: ${lighten(bg, 0.08)};
      --color-border:    ${lighten(bg, 0.10)};
      --color-accent:    ${accent};
      background-color: ${bg};
    }
  `
}

function loadStored() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {} } catch { return {} }
}

const stored = typeof window !== 'undefined' ? loadStored() : {}

export const theme = writable({
  bg:     stored.bg     || '#0f1117',
  accent: stored.accent || '#0072FF',
})

if (typeof window !== 'undefined') {
  theme.subscribe(t => {
    applyTheme(t.bg, t.accent)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(t))
  })
}

// Substrate has no /auth/me — theme persists in localStorage only.
// Project clones extending the substrate can override this.
export async function loadThemeFromApi() { /* no-op in substrate */ }
