/**
 * Auto-derive a concise session title from the user's message.
 * Simple truncation approach — no complex pattern matching.
 */

const MAX_TITLE_LEN = 28

/**
 * Extract a meaningful title from a user message.
 * Returns the cleaned title, or null if empty.
 */
export function deriveSessionTitle(raw: string): string | null {
  if (!raw || typeof raw !== 'string') return null
  let text = raw.trim().replace(/\s+/g, ' ')
  if (!text) return null

  // Take first sentence (split on 。！？.!?\n)
  const m = text.match(/^.*?[。！？.!?\n]/)
  if (m) text = m[0].replace(/[。！？.!?\n]$/, '').trim()

  if (text.length < 2) return null

  // Truncate
  if (text.length > MAX_TITLE_LEN) {
    const hasCJK = /[\u4e00-\u9fff]/.test(text)
    if (hasCJK) {
      text = text.slice(0, MAX_TITLE_LEN) + '…'
    } else {
      const cut = text.slice(0, MAX_TITLE_LEN)
      const lastSp = cut.lastIndexOf(' ')
      text = (lastSp > MAX_TITLE_LEN * 0.5 ? cut.slice(0, lastSp) : cut) + '…'
    }
  }

  return text || null
}

/**
 * Returns true if the given title is a placeholder that should be replaced.
 */
export function isPlaceholderTitle(title: string | null | undefined): boolean {
  if (!title) return true
  const t = title.trim()
  return !t || t === '新对话' || t === '新会话' || t === 'New Session' || t === 'Untitled Session'
}