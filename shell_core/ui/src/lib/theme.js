// Theme handling — three named themes, persisted by name in localStorage.
//
// Each theme pins a base color + an explicit background gradient + an accent.
// The accent drives accent-derived washes for the active-pill highlight and
// the avatar orb so a single theme switch shifts the whole canvas mood.
import { writable } from 'svelte/store'

const STORAGE_KEY = 'dos_theme'

export const THEMES = [
  {
    name: 'Solid Charcoal',
    base: '#17171c',
    background: 'linear-gradient(180deg, #1a1a1f 0%, #141418 100%)',
    accent: '#fbbf24',
  },
  {
    name: 'Twilight',
    base: '#06051a',
    background: 'linear-gradient(135deg, #06051a 0%, #150929 100%)',
    accent: '#ec4899',
  },
  {
    name: 'Slate',
    base: '#1a1f2a',
    background: 'linear-gradient(180deg, #1a1f2a 0%, #252b35 100%)',
    accent: '#38bdf8',
  },
]

const DEFAULT_THEME = 'Solid Charcoal'

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

function hexToRgb(hex) {
  return [
    parseInt(hex.slice(1,3),16),
    parseInt(hex.slice(3,5),16),
    parseInt(hex.slice(5,7),16),
  ]
}

export function applyTheme(t) {
  if (typeof document === 'undefined') return
  let el = document.getElementById('dos-theme')
  if (!el) {
    el = document.createElement('style')
    el.id = 'dos-theme'
    document.head.appendChild(el)
  }
  const { base, background, accent } = t

  // Active-row highlight — 90° linear gradient from 20% accent → 3% accent.
  // Paired with a solid 2px left bar (--accent-bar) in CSS. Pure accent
  // rgba band, no hue rotation.
  const [ar, ag, ab] = hexToRgb(accent)
  const accentRowGrad =
    `linear-gradient(90deg, rgba(${ar},${ag},${ab},0.20), rgba(${ar},${ag},${ab},0.03))`

  // Avatar orb — same hue pair fully saturated with a stronger glow.
  const orbA   = washFrom(accent,   0, 1)
  const orbB   = washFrom(accent,  90, 1)
  const orbGlow = washFrom(accent,  0, 0.4)
  const orbGrad = `linear-gradient(135deg, ${orbA}, ${orbB})`

  // Soft orb — canvas-toned variant for decorative empty-state moments.
  const orbSoftA    = washFrom(accent,   0, 0.30)
  const orbSoftB    = washFrom(accent,  90, 0.20)
  const orbSoftGlow = washFrom(accent,   0, 0.20)
  const orbSoftGrad = `linear-gradient(135deg, ${orbSoftA}, ${orbSoftB})`

  el.textContent = `
    :root, html, body {
      --color-accent:     ${accent};
      --app-base:         ${base};
      --app-gradient:     ${background};
      --accent-bar:       ${accent};
      --accent-row-grad:  ${accentRowGrad};
      --orb-grad:         ${orbGrad};
      --orb-glow:         ${orbGlow};
      --orb-soft-grad:    ${orbSoftGrad};
      --orb-soft-glow:    ${orbSoftGlow};
      background-color:   ${base};
    }
  `
}

function findTheme(name) {
  return THEMES.find(t => t.name === name) || THEMES[0]
}

function loadStored() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY))
    return (raw && raw.name) || DEFAULT_THEME
  } catch { return DEFAULT_THEME }
}

const storedName = typeof window !== 'undefined' ? loadStored() : DEFAULT_THEME

export const theme = writable(findTheme(storedName))

export function setTheme(name) {
  theme.set(findTheme(name))
}

if (typeof window !== 'undefined') {
  theme.subscribe(t => {
    applyTheme(t)
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ name: t.name }))
  })
}

// Substrate has no /auth/me — theme persists in localStorage only.
// Project clones extending the substrate can override this.
export async function loadThemeFromApi() { /* no-op in substrate */ }
