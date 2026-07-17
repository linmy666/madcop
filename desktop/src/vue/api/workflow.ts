// Vue API layer — uses vue/api/client (port 8765), not React src/api.
import { getApiUrl } from './client'
import type { WorkflowNode, WorkflowEdge, WorkflowRun } from '../../types/workflow'

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

const BASE = '/api/workflows'

async function apiGet(path: string): Promise<any> {
  const r = await fetch(getApiUrl(path))
  if (!r.ok) throw new Error(`GET ${path} failed: ${r.status}`)
  return r.json()
}

async function apiPost(path: string, body: any): Promise<any> {
  const r = await fetch(getApiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const t = await r.text().catch(() => '')
    throw new Error(`POST ${path} failed: ${r.status} ${t}`)
  }
  return r.json()
}

async function apiPut(path: string, body: any): Promise<any> {
  const r = await fetch(getApiUrl(path), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`PUT ${path} failed: ${r.status}`)
  return r.json()
}

async function apiDelete(path: string): Promise<void> {
  const r = await fetch(getApiUrl(path), { method: 'DELETE' })
  if (!r.ok) throw new Error(`DELETE ${path} failed: ${r.status}`)
}

export async function listWorkflows(): Promise<Workflow[]> {
  const d = await apiGet(BASE)
  return d.workflows || []
}

export async function getWorkflow(id: string): Promise<Workflow | null> {
  try {
    return await apiGet(`${BASE}/${id}`)
  } catch {
    return null
  }
}

export async function createWorkflow(body: Partial<Workflow>): Promise<Workflow> {
  return apiPost(BASE, body)
}

export async function updateWorkflow(id: string, body: Partial<Workflow>): Promise<Workflow> {
  return apiPut(`${BASE}/${id}`, body)
}

export async function deleteWorkflow(id: string): Promise<void> {
  await apiDelete(`${BASE}/${id}`)
}

export async function runWorkflow(
  id: string,
  input: Record<string, unknown> = {},
): Promise<WorkflowRun> {
  return apiPost(`${BASE}/${id}/run`, { input })
}

export async function listRuns(workflowId: string): Promise<WorkflowRun[]> {
  const d = await apiGet(`${BASE}/${workflowId}/runs`)
  return d.runs || []
}

export async function listNodeTypes(): Promise<NodeTypeMeta[]> {
  const d = await apiGet(`${BASE}/_meta/node-types`)
  return d.node_types || []
}
