import { api } from './client'
import { getApiUrl } from './client'
import type { TraceCaptureSettings, TraceSessionList } from '../../types/trace'

/** A single agent-step node in a conversation's trace DAG. Matches the
 *  backend TraceNode (madcop/agent/trace.py). */
export interface TraceNode {
  id: string
  conversation_id: string
  parent_id: string | null
  node_type: string        // 'llm_call' | 'tool_call' | 'tool_result' | 'user_input' | ...
  status: string           // 'pending' | 'running' | 'done' | 'error' | 'superseded'
  label: string
  input: string
  output: string
  error: string
  created_at: number
  completed_at: number | null
  depth: number
}

export const tracesApi = {
  list(options?: { limit?: number; offset?: number; query?: string }) {
    const params = new URLSearchParams()
    if (options?.limit !== undefined) params.set('limit', String(options.limit))
    if (options?.offset !== undefined) params.set('offset', String(options.offset))
    if (options?.query) params.set('q', options.query)
    const suffix = params.toString() ? `?${params}` : ''
    return api.get<TraceSessionList>(`/api/traces${suffix}`)
  },

  /** Fetch the full trace DAG for one conversation. Returns the raw array. */
  async getSession(sessionId: string): Promise<TraceNode[]> {
    const res = await fetch(getApiUrl(`/api/sessions/${encodeURIComponent(sessionId)}/trace`))
    if (!res.ok) throw new Error(`trace fetch failed: ${res.status}`)
    const data = await res.json()
    return (data.trace || data.nodes || []) as TraceNode[]
  },

  getSettings() {
    return api.get<TraceCaptureSettings>('/api/traces/settings')
  },

  updateSettings(settings: Partial<Pick<TraceCaptureSettings, 'enabled'>>) {
    return api.put<TraceCaptureSettings>('/api/traces/settings', settings)
  },
}
