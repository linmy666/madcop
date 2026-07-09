/** Stub for desktop host — desktop-only API not available in Vue build.
 * We auto-detect Electron by checking `window.electronApi` (injected by
 * the Electron preload) so file pickers, IPC, and other desktop features
 * work inside the Electron wrapper. */
export interface DesktopHost {
  isDesktop: boolean
}

declare global {
  interface Window {
    electronApi?: unknown
    madcopDesktop?: unknown
    desktopHost?: unknown
  }
}

export function getDesktopHost(): DesktopHost {
  if (typeof window === 'undefined') return { isDesktop: false }
  if (window.electronApi || window.madcopDesktop || window.desktopHost) return { isDesktop: true }
  // Fallback: detect by user agent (Electron's UA contains "Electron/x.y.z")
  if (typeof navigator !== 'undefined' && /Electron\//.test(navigator.userAgent)) {
    return { isDesktop: true }
  }
  return { isDesktop: false }
}
