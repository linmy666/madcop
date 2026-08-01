/**
 * Sprint 6 — Knowledge Canvas API client.
 * Talks to the FastAPI brain graph routes (madcop/server/routes/brain_graph.py).
 */
import { api } from './client'

export interface BrainNode {
  id: string
  slug: string
  label: string
  title: string
  type: string
  tags: string[]
  body: string
  preview: string
  updatedAt: string
  createdAt: string
  linksIn?: { slug: string; context: string }[]
  linksOut?: { slug: string; context: string }[]
}

export interface BrainEdge {
  id: string
  source: string
  target: string
  label: string
  context: string
  direction: string
}

export interface BrainGraph {
  nodes: BrainNode[]
  edges: BrainEdge[]
}

export const brainApi = {
  /** Full graph for the canvas. Returns {nodes, edges} even when the
   * backend is unavailable (404 → null from the shared client), so the
   * canvas never crashes on `.nodes`. */
  graph: async (workspace?: string): Promise<BrainGraph> => {
    const query = workspace ? `?workspace=${encodeURIComponent(workspace)}` : ''
    const res = await api.get<BrainGraph | null>(`/api/brain/graph${query}`)
    if (!res || typeof res !== 'object') {
      const e = new Error('知识画布接口不可用（后端可能未加载该路由，请重启后端）')
      ;(e as any).unavailable = true
      throw e
    }
    return {
      nodes: Array.isArray(res.nodes) ? res.nodes : [],
      edges: Array.isArray(res.edges) ? res.edges : [],
    }
  },

  /** Single node detail (for the NodeDetail drawer). */
  node: (slug: string) => api.get<{ node: BrainNode }>(`/api/brain/node/${encodeURIComponent(slug)}`),

  /** Create or update a node (canvas double-click → new). */
  saveNode: (input: { slug: string; title: string; body?: string; type?: string; tags?: string[] }, workspace?: string) => {
    const query = workspace ? `?workspace=${encodeURIComponent(workspace)}` : ''
    return api.post<{ ok: boolean; node: BrainNode }>(`/api/brain/node${query}`, {
      slug: input.slug,
      title: input.title,
      body: input.body ?? '',
      type: input.type ?? 'concept',
      tags: input.tags ?? [],
    })
  },

  /** Add a directed edge between two existing nodes. */
  link: (fromSlug: string, toSlug: string, context = '') =>
    api.post<{ ok: boolean; from: string; to: string; error?: string }>(
      `/api/brain/link?from_slug=${encodeURIComponent(fromSlug)}&to_slug=${encodeURIComponent(toSlug)}&context=${encodeURIComponent(context)}`,
    ),

  /** Delete a node (idempotent). */
  deleteNode: (slug: string) =>
    api.delete<{ ok: boolean; slug: string }>(`/api/brain/node/${encodeURIComponent(slug)}`),
}
