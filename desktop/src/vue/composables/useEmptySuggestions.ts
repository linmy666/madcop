/**
 * useEmptySuggestions — shared builder for the "what can I ask?" chips
 * shown on empty-state screens (EmptySession page + ActiveSession's
 * empty-session hero).
 *
 * Extracted from EmptySession.vue so both empty states show the same
 * workspace-aware suggestions. v2 — suggestions come from the
 * WORKSPACE'S REAL CONTENT (via /api/workspace/ls): code folders get
 * code suggestions, document folders get summary suggestions, anything
 * else gets generic agent starters. Skill count comes from the skills
 * API instead of a stale localStorage key.
 */
import { ref } from 'vue'

const suggestions = ref<string[]>(['搜一下最新的技术动态'])

const CODE_EXTS = new Set(['py', 'js', 'ts', 'tsx', 'jsx', 'html', 'css', 'go', 'rs', 'java', 'vue', 'sh'])
const DOC_EXTS = new Set(['xlsx', 'docx', 'pptx', 'csv', 'pdf', 'md'])

async function rebuildSuggestions() {
  const out: string[] = []
  const ws = (() => { try { return localStorage.getItem('madcop_workspace_dir') || '' } catch { return '' } })()
  const projectName = ws ? (ws.split('/').pop() || '项目') : ''
  try {
    const res = await fetch(getApiUrl(`/api/workspace/ls?dir=${encodeURIComponent(ws)}`))
    const data = await res.json()
    const entries: { name: string; is_dir: boolean }[] = data.entries || []
    const exts = entries
      .filter((e: any) => !e.is_dir)
      .map((e: any) => (e.name.split('.').pop() || '').toLowerCase())
    const hasCode = exts.some((e: string) => CODE_EXTS.has(e))
    const docCount = exts.filter((e: string) => DOC_EXTS.has(e)).length
    if (hasCode) {
      out.push(`分析 ${projectName} 项目的代码结构`)
      out.push(`给 ${projectName} 写一份单元测试`)
    }
    if (docCount >= 2) {
      out.push(`汇总 ${projectName} 目录里 ${docCount} 份文档的要点`)
    }
  } catch { /* workspace unreachable — fall through to generic starters */ }
  if (!out.length) {
    out.push('帮我把一个想法变成可交互的网页原型')
    out.push('帮我研究一个课题，整理成带来源的报告')
  }
  // Real skill count from the skills API (not a stale localStorage key).
  try {
    const res = await fetch(getApiUrl('/api/agents/skills'))
    const data = await res.json()
    const n = Array.isArray(data) ? data.length : (Array.isArray(data.skills) ? data.skills.length : 0)
    if (n > 0) out.push(`查看我已保存的 ${n} 个技能`)
  } catch { /* skills optional */ }
  out.push('搜一下最新的技术动态')
  suggestions.value = out.slice(0, 5)
}

export function useEmptySuggestions() {
  void rebuildSuggestions()
  return { suggestions }
}
