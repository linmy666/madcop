// v3.0 — MadCop appearance composable (Vue 3)
// Mirrors the React useMadcopTheme() hook. Reads localStorage,
// applies [data-madcop-theme] to <html>, exposes setAppearance.

import { ref, watch, onMounted, onUnmounted } from 'vue'

export type Appearance = 'light' | 'dark' | 'sepia'
const STORAGE_KEY = 'madcop:appearance:v1'

function readInitial(): Appearance {
  if (typeof window === 'undefined') return 'light'
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'light' || v === 'dark' || v === 'sepia') return v
  } catch {}
  return 'light'
}

const appearance = ref<Appearance>(readInitial())

function applyToHtml(a: Appearance) {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-madcop-theme', a)
  document.documentElement.setAttribute('data-theme', a)
}

function setAppearance(next: Appearance) {
  appearance.value = next
  try { localStorage.setItem(STORAGE_KEY, next) } catch {}
  applyToHtml(next)
}

let mq: MediaQueryList | null = null
const onChange = (e: MediaQueryListEvent) => {
  try {
    if (!localStorage.getItem(STORAGE_KEY)) {
      setAppearance(e.matches ? 'dark' : 'light')
    }
  } catch {}
}

onMounted(() => {
  applyToHtml(appearance.value)
  mq = window.matchMedia('(prefers-color-scheme: dark)')
  mq.addEventListener('change', onChange)
})
onUnmounted(() => { mq?.removeEventListener('change', onChange) })

watch(appearance, (v) => applyToHtml(v))

export function useAppearance() {
  return { appearance, setAppearance }
}
