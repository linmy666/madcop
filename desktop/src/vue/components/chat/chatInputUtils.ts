/** Small pure helpers extracted from ChatInput.vue */

export function isDesktopRuntime(): boolean {
  try {
    return typeof window !== 'undefined' &&
      (navigator.userAgent.includes('Electron') ||
       navigator.userAgent.includes('madcop') ||
       location.protocol === 'file:')
  } catch {
    return false
  }
}

export function isMobileViewport(): boolean {
  try {
    return typeof window !== 'undefined' && window.innerWidth < 768
  } catch {
    return false
  }
}

export function shouldSubmitOnEnter(event: KeyboardEvent, behavior: string): boolean {
  if (event.key !== 'Enter') return false
  if (event.shiftKey) return false
  if (behavior === 'enter') return true
  if (behavior === 'ctrl-enter' && (event.ctrlKey || event.metaKey)) return true
  return false
}

export type ComposerAttachment = {
  id: string
  name: string
  type: 'file' | 'image' | 'text'
  path?: string
  isDirectory?: boolean
  lineStart?: number
  lineEnd?: number
  note?: string
  quote?: string
  mimeType?: string
  previewUrl?: string
  data?: string
}
