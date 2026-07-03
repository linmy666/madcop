// v2.7.0 — WorkflowsListPage: shows all saved workflows + create new.

import { useEffect, useState } from 'react'
import {
  listWorkflows,
  createWorkflow,
  deleteWorkflow,
  runWorkflow,
  type Workflow,
  type NodeTypeMeta,
} from '../api/workflow'
import { listNodeTypes } from '../api/workflow'
import { WorkflowEditor } from '../components/workflow/WorkflowEditor'
import type { Edge, Node } from '@xyflow/react'

export function WorkflowsListPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [nodeTypes, setNodeTypes] = useState<NodeTypeMeta[]>([])
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState<string>('')
  const [editingNodes, setEditingNodes] = useState<Node[]>([])
  const [editingEdges, setEditingEdges] = useState<Edge[]>([])
  const [loading, setLoading] = useState(true)
  const [isRunning, setIsRunning] = useState(false)
  const [currentNodeId, setCurrentNodeId] = useState<string | null>(null)
  const [runResult, setRunResult] = useState<string | null>(null)

  const refresh = async () => {
    setLoading(true)
    try {
      const [list, types] = await Promise.all([listWorkflows(), listNodeTypes()])
      setWorkflows(list)
      setNodeTypes(types)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const handleNew = async () => {
    // v2.7.0: Always include start + end nodes; LLM node added in editor.
    // Don't depend on nodeTypes.length — if the metadata API was
    // slow / failed, the user can still create a workflow.
    const wf = await createWorkflow({
      name: '未命名工作流',
      description: '',
      nodes: [
        { id: 'start-1', type: 'start', position: { x: 100, y: 200 }, data: { label: '开始' } },
        { id: 'end-1', type: 'end', position: { x: 500, y: 200 }, data: { label: '结束' } },
      ],
      edges: [],
    })
    await refresh()
    setEditingId(wf.id)
    setEditingName(wf.name)
    setEditingNodes(wf.nodes as unknown as Node[])
    setEditingEdges(wf.edges as unknown as Edge[])
  }

  const handleEdit = (wf: Workflow) => {
    setEditingId(wf.id)
    setEditingName(wf.name)
    setEditingNodes(wf.nodes as unknown as Node[])
    setEditingEdges(wf.edges as unknown as Edge[])
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确定删除这个工作流？')) return
    await deleteWorkflow(id)
    await refresh()
  }

  const handleSave = async (nodes: Node[], edges: Edge[]) => {
    if (!editingId) return
    const r = await fetch(`/api/workflows/${editingId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: editingName,
        nodes: nodes.map((n) => ({
          id: n.id,
          type: n.type,
          position: n.position,
          data: n.data,
        })),
        edges: edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
        })),
      }),
    })
    if (!r.ok) throw new Error(`Save failed: ${r.status}`)
    await refresh()
  }

  const handleRun = async () => {
    if (!editingId) return
    setIsRunning(true)
    setCurrentNodeId(null)
    setRunResult(null)
    try {
      const run = await runWorkflow(editingId, { input: '你好' })
      setRunResult(JSON.stringify(run, null, 2))
    } catch (e) {
      setRunResult(`Error: ${(e as Error).message}`)
    } finally {
      setIsRunning(false)
    }
  }

  const handleBack = async () => {
    setEditingId(null)
    setEditingName('')
    setEditingNodes([])
    setEditingEdges([])
    setRunResult(null)
    await refresh()
  }

  if (editingId) {
    return (
      <div style={{ width: '100%', height: '100vh' }}>
        <WorkflowEditor
          workflowId={editingId}
          workflowName={editingName}
          initialNodes={editingNodes}
          initialEdges={editingEdges}
          onSave={handleSave}
          onRun={handleRun}
          isRunning={isRunning}
          currentNodeId={currentNodeId}
          onBack={handleBack}
        />
        {runResult && (
          <div
            style={{
              position: 'fixed',
              bottom: 16,
              left: '50%',
              transform: 'translateX(-50%)',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: 8,
              padding: 16,
              maxWidth: 720,
              maxHeight: 240,
              overflow: 'auto',
              boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
              fontSize: 12,
              fontFamily: 'monospace',
              color: 'var(--color-text-primary)',
              whiteSpace: 'pre-wrap',
              zIndex: 50,
            }}
            onClick={() => setRunResult(null)}
          >
            <strong>运行结果 (点击关闭):</strong>
            <pre style={{ margin: '8px 0 0', fontSize: 11 }}>{runResult}</pre>
          </div>
        )}
      </div>
    )
  }

  return (
    <div
      style={{
        maxWidth: 960,
        margin: '0 auto',
        padding: '40px 20px',
        color: 'var(--color-text-primary)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 24,
        }}
      >
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>工作流</h1>
        <button
          onClick={handleNew}
          style={{
            padding: '8px 16px',
            background: 'var(--color-brand)',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 14,
            opacity: nodeTypes.length === 0 ? 0.7 : 1,
          }}
        >
          + 新建工作流
        </button>
      </div>

      {loading ? (
        <div style={{ color: 'var(--color-text-secondary)' }}>加载中…</div>
      ) : workflows.length === 0 ? (
        <div
          style={{
            padding: '40px 20px',
            textAlign: 'center',
            color: 'var(--color-text-secondary)',
            background: 'var(--color-surface-container-low)',
            borderRadius: 8,
          }}
        >
          还没有工作流。点"新建工作流"创建一个。
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
          {workflows.map((wf) => (
            <div
              key={wf.id}
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: 8,
                padding: 16,
                cursor: 'pointer',
              }}
              onClick={() => handleEdit(wf)}
            >
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>{wf.name}</div>
              <div style={{ fontSize: 12, color: 'var(--color-text-tertiary)', marginBottom: 12 }}>
                {wf.description || '无描述'} · {wf.nodes.length} 节点 · v{wf.version}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    handleEdit(wf)
                  }}
                  style={{
                    padding: '4px 10px',
                    background: 'var(--color-surface-container-high)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 4,
                    color: 'var(--color-text-primary)',
                    cursor: 'pointer',
                    fontSize: 12,
                  }}
                >
                  编辑
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    handleDelete(wf.id)
                  }}
                  style={{
                    padding: '4px 10px',
                    background: 'transparent',
                    border: '1px solid #ef4444',
                    color: '#ef4444',
                    borderRadius: 4,
                    cursor: 'pointer',
                    fontSize: 12,
                  }}
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}