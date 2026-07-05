// v3.0 — useMobileViewport (Vue 3)
// Replacement for the React useMobileViewport.ts that was being bundled
// into the Vue build. Returns a ref<boolean>.
import { ref, onMounted, onUnmounted } from 'vue'

const MOBILE_VIEWPORT_QUERY = '(max-width: 767px)'

export function useMobileViewport() {
  const isMobile = ref(false)
  let mediaQuery: MediaQueryList | null = null

  function handleChange(e: MediaQueryListEvent) {
    isMobile.value = e.matches
  }

  onMounted(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    mediaQuery = window.matchMedia(MOBILE_VIEWPORT_QUERY)
    isMobile.value = mediaQuery.matches
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleChange)
    } else {
      mediaQuery.addListener(handleChange)
    }
  })

  onUnmounted(() => {
    if (!mediaQuery) return
    if (typeof mediaQuery.removeEventListener === 'function') {
      mediaQuery.removeEventListener('change', handleChange)
    } else {
      mediaQuery.removeListener(handleChange)
    }
  })

  return isMobile
}
