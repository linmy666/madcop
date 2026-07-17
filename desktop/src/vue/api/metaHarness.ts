import { api } from './client'

export const metaHarnessApi = {
  status: () => api.get<{
    active: Record<string, unknown>
    archive_best: Record<string, unknown> | null
    archive_count: number
    axes: unknown[]
  }>('/api/meta-harness/status'),

  candidates: () => api.get<{ candidates: Array<Record<string, unknown>> }>(
    '/api/meta-harness/candidates',
  ),

  promote: (id?: string) =>
    api.post<{ ok: boolean; active: Record<string, unknown> }>(
      '/api/meta-harness/promote',
      id ? { id } : {},
    ),

  run: (body: {
    iterations?: number
    suite?: string
    proposer?: string
    promote?: boolean
    seed?: number
  }) => api.post<Record<string, unknown>>('/api/meta-harness/run', body),

  axes: () => api.get<{ axes: unknown[] }>('/api/meta-harness/axes'),
}
