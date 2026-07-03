// v2.7.0 — Workflow REST API client.
import type { WorkflowNode, WorkflowEdge, WorkflowRun } from '../../types/workflow'

const BASE = '/api/workflows'

export interface Workflow {
  id: string
  name: string
  description: string
  version: number
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  variables: unknown[]
  created_at: number
  updated_at: number
}

export interface NodeTypeMeta {
  type: string
  label: string
  description: string
  category: string
}

export async function listWorkflows(): Promise<Workflow[]> {
  const r = await fetch(BASE)
  const d = await r.json()
  return d.workflows || []
}

export async function getWorkflow(id: string): Promise<Workflow | null> {
  const r = await fetch(`${BASE}/${id}`)
  if (r.status === 404) return null
  return r.json()
}

export async function createWorkflow(body: Partial<Workflow>): Promise<Workflow> {
  const r = await fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return r.json()
}

export async function updateWorkflow(id: string, body: Partial<Workflow>): Promise<Workflow> {
  const r = await fetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return r.json()
}

export async function deleteWorkflow(id: string): Promise<void> {
  await fetch(`${BASE}/${id}`, { method: 'DELETE' })
}

export async function runWorkflow(
  id: string,
  input: Record<string, unknown> = {}
): Promise<WorkflowRun> {
  const r = await fetch(`${BASE}/${id}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input }),
  })
  if (!r.ok) {
    const t = await r.text()
    throw new Error(`Run failed: ${r.status} ${t}`)
  }
  return r.json()
}

export async function listRuns(workflowId: string): Promise<WorkflowRun[]> {
  const r = await fetch(`${BASE}/${workflowId}/runs`)
  const d = await r.json()
  return d.runs || []
}

export async function listNodeTypes(): Promise<NodeTypeMeta[]> {
  const r = await fetch(`${BASE}/_meta/node-types`)
  const d = await r.json()
  return d.node_types || []
}