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
  /** Full graph for the canvas. */
  graph: (workspace?: string) => {
    const query = workspace ? `?workspace=${encodeURIComponent(workspace)}` : ''
    return api.get<BrainGraph>(`/api/brain/graph${query}`)
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
