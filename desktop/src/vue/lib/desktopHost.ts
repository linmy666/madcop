/** Stub for desktop host — desktop-only API not available in Vue build */
export interface DesktopHost {
  isDesktop: boolean
}

export function getDesktopHost(): DesktopHost {
  return { isDesktop: false }
}
