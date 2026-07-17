/**
 * Sanitize agent stream text for bubbles / detail UI (not for model I/O).
 */

const ERROR_RULES: { re: RegExp; label: string }[] = [
  { re: /model is not found|not_found_error|model.?not.?found/i, label: '模型不可用' },
  { re: /Error code:\s*404|HTTP 404/i, label: '接口未找到 (404)' },
  { re: /Error code:\s*401|unauthorized|invalid.?api.?key/i, label: '鉴权失败' },
  { re: /Error code:\s*429|rate.?limit/i, label: '请求过于频繁' },
  { re: /timeout|timed out/i, label: '响应超时' },
  { re: /ReAct engine error/i, label: '执行出错' },
  { re: /LLM 调用失败|LLM call failed/i, label: '模型调用失败' },
]

/** Strip common markdown emphasis / fences for compact UI labels. */
export function stripMarkdownLite(text: string): string {
  if (!text) return ''
  let s = text
  s = s.replace(/```[\s\S]*?```/g, ' ')
  s = s.replace(/`([^`]+)`/g, '$1')
  s = s.replace(/\*\*([^*]+)\*\*/g, '$1')
  s = s.replace(/__([^_]+)__/g, '$1')
  s = s.replace(/\*([^*]+)\*/g, '$1')
  s = s.replace(/_([^_]+)_/g, '$1')
  s = s.replace(/^#{1,6}\s+/gm, '')
  s = s.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
  s = s.replace(/\s+/g, ' ').trim()
  return s
}

export function mapEngineErrorLabel(text: string): string | null {
  if (!text) return null
  for (const { re, label } of ERROR_RULES) {
    if (re.test(text)) return label
  }
  if (/^\s*\[ReAct engine error/i.test(text) || /engine error/i.test(text)) {
    return '执行出错'
  }
  return null
}

/**
 * Human-facing short text for bubbles and detail previews.
 */
export function sanitizeAgentDisplayText(
  text: string,
  maxLen = 48,
): string {
  if (!text) return ''
  const err = mapEngineErrorLabel(text)
  if (err) return err
  let s = stripMarkdownLite(text)
  // Drop JSON-ish dumps
  if (s.startsWith('{') && s.includes("'error'")) {
    return mapEngineErrorLabel(s) || '执行出错'
  }
  if (s.length <= maxLen) return s
  return s.slice(0, maxLen - 1) + '…'
}
