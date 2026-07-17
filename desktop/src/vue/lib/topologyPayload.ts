/**
 * Build real engine payload for /api/agents/networks/run-adhoc
 * from canvas GraphNodeData / GraphEdgeData.
 */

export interface TopologyNodeIn {
  id: string
  label: string
  agentId?: string
  role?: string
  model?: string
  systemPrompt?: string
  tools?: string[]
  x?: number
  y?: number
  status?: string
  detail?: string
}

export interface TopologyEdgeIn {
  id?: string
  from: string
  to: string
  label?: string
  type?: string
}

export function buildRunAdhocPayload(
  input: string,
  nodes: TopologyNodeIn[],
  edges: TopologyEdgeIn[],
  name = 'Ad-hoc',
) {
  return {
    name,
    input: input.trim() || '执行任务',
    nodes: nodes.map((n) => ({
      id: n.id,
      name: n.label || n.id,
      agentId: n.agentId || n.role || n.id,
      model: n.model || '',
      systemPrompt: n.systemPrompt || '',
      tools: Array.isArray(n.tools) ? n.tools : [],
      // engine also reads description from registry; pass via name fields
      description: n.systemPrompt || n.detail || '',
    })),
    edges: edges.map((e) => ({
      from: e.from,
      to: e.to,
      label: e.label || '',
    })),
  }
}

export function applyStepStatuses<T extends { id: string; status?: string }>(
  nodes: T[],
  steps: Array<{ node_id: string; status: string }>,
): T[] {
  const map = new Map(steps.map((s) => [s.node_id, s.status]))
  return nodes.map((n) => {
    const st = map.get(n.id)
    if (!st) return { ...n, status: n.status === 'running' ? 'completed' : n.status }
    if (st === 'error') return { ...n, status: 'failed' }
    return { ...n, status: 'completed' }
  })
}
