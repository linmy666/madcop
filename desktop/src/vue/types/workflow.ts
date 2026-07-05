// v2.7.0 — Workflow type definitions (shared with backend).

export interface WorkflowNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: Record<string, unknown>
}

export interface WorkflowEdge {
  id: string
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
  data?: Record<string, unknown>
}

export interface WorkflowRun {
  id: string
  workflow_id: string
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed'
  input: Record<string, unknown>
  output: Record<string, unknown>
  current_node_id: string | null
  error: string | null
  started_at: number | null
  completed_at: number | null
  created_at: number
}

export interface NodeRun {
  id: string
  run_id: string
  node_id: string
  status: 'pending' | 'running' | 'success' | 'failed' | 'skipped'
  input: Record<string, unknown>
  output: Record<string, unknown>
  duration_ms: number | null
  error: string | null
  started_at: number | null
  completed_at: number | null
}