// Theme handling — persistent bg/accent presets in localStorage.
//
// Spatial-glass model: bg is the deep base color; accent drives a three-wash
// radial gradient (accent, accent+90°, accent-45°) layered over the base.
// Picking a new accent shifts the whole canvas mood.
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

function hexToHsl(hex) {
  const r = parseInt(hex.slice(1,3),16) / 255
  const g = parseInt(hex.slice(3,5),16) / 255
  const b = parseInt(hex.slice(5,7),16) / 255
  const max = Math.max(r,g,b), min = Math.min(r,g,b)
  let h = 0, s = 0
  const l = (max + min) / 2
  if (max !== min) {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break
      case g: h = (b - r) / d + 2; break
      case b: h = (r - g) / d + 4; break
    }
    h /= 6
  }
  return [h * 360, s * 100, l * 100]
}

function washFrom(accent, hueShift, alpha) {
  const [h, s, l] = hexToHsl(accent)
  // Lift lightness a touch on dark accents so the wash actually glows.
  const lift = l < 50 ? Math.min(70, l + 18) : l
  const hh = ((h + hueShift) % 360 + 360) % 360
  return `hsla(${hh.toFixed(1)}, ${s.toFixed(1)}%, ${lift.toFixed(1)}%, ${alpha})`
}

export function applyTheme(bg, accent) {
  if (typeof document === 'undefined') return
  let el = document.getElementById('dos-theme')
  if (!el) {
    el = document.createElement('style')
    el.id = 'dos-theme'
    document.head.appendChild(el)
  }
  const wash1 = washFrom(accent,   0, 0.28)
  const wash2 = washFrom(accent,  90, 0.20)
  const wash3 = washFrom(accent, -45, 0.14)
  const gradient =
    `radial-gradient(ellipse 80% 60% at 20% 0%, ${wash1}, transparent), ` +
    `radial-gradient(ellipse 60% 80% at 100% 100%, ${wash2}, transparent), ` +
    `radial-gradient(ellipse 50% 50% at 60% 50%, ${wash3}, transparent)`

  // Active-pill highlight — same two-stop linear gradient the JSX example
  // uses (135° from primary accent into a +90° hue-shifted twin), plus a
  // soft outer glow at the same hue as the primary. Consumed by the
  // .active-pill class for tabs, model picker selection, etc.
  const pillA    = washFrom(accent,   0, 0.18)
  const pillB    = washFrom(accent,  90, 0.10)
  const pillGlow = washFrom(accent,   0, 0.25)
  const activePill = `linear-gradient(135deg, ${pillA}, ${pillB})`

  el.textContent = `
    :root, html, body {
      --color-surface-1: ${bg};
      --color-surface-2: ${lighten(bg, 0.04)};
      --color-surface-3: ${lighten(bg, 0.08)};
      --color-border:    ${lighten(bg, 0.10)};
      --color-accent:    ${accent};
      --app-base:        ${bg};
      --app-gradient:    ${gradient};
      --active-pill-grad: ${activePill};
      --active-pill-glow: ${pillGlow};
      background-color:  ${bg};
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
