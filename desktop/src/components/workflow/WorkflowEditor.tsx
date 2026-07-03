// v2.7.0 — WorkflowEditor: main React Flow canvas for the workflow editor.
//
// Adapts AutoGen Studio's builder.tsx (MIT) for MadCop's stack:
//   - React Flow (drag/drop nodes + edges)
//   - Sidebar with node library (Start / LLM / End)
//   - Top toolbar (Save / Run / Status)
//   - Right side panel for node config
//
// Phase 1 MVP: linear workflow, 3 node types, save + run.

import { useCallback, useEffect, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type Edge,
  type Node,
  type NodeTypes,
  Handle,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { listNodeTypes, type NodeTypeMeta } from '../../api/workflow'

// --------------------------------------------------------------------------- #
// Custom node types (visual presentation only — execution lives in backend)
// --------------------------------------------------------------------------- #

interface NodeData extends Record<string, unknown> {
  label?: string
  type?: string
  [key: string]: unknown
}

function BaseNode({
  data,
  type,
  selected = false,
}: {
  data: NodeData
  type: string
  selected?: boolean
}) {
  const label = data.label || type
  const colorByType: Record<string, string> = {
    start: '#10b981',
    llm: '#7c3aed',
    tool: '#f97316',
    code: '#3b82f6',
    condition: '#ef4444',
    loop: '#8b5cf6',
    web_search: '#06b6d4',
    knowledge: '#ec4899',
    http_request: '#f59e0b',
    input: '#6366f1',
    aggregator: '#14b8a6',
    variable: '#84cc16',
    end: '#f59e0b',
  }
  const color = colorByType[type] || '#64748b'

  return (
    <div
      style={{
        background: 'var(--color-surface)',
        border: selected ? `2px solid ${color}` : '1px solid var(--color-border)',
        borderRadius: 8,
        padding: '12px 16px',
        minWidth: 180,
        boxShadow: selected
          ? '0 4px 12px rgba(0,0,0,0.15)'
          : '0 1px 3px rgba(0,0,0,0.08)',
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: color, width: 8, height: 8 }}
      />
      <div
        style={{
          fontSize: 10,
          textTransform: 'uppercase',
          letterSpacing: 1,
          color: color,
          fontWeight: 600,
          marginBottom: 4,
        }}
      >
        {type}
      </div>
      <div style={{ fontSize: 13, color: 'var(--color-text-primary)', fontWeight: 500 }}>
        {label}
      </div>
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: color, width: 8, height: 8 }}
      />
    </div>
  )
}

const NODE_TYPE_REGISTRY: NodeTypes = {
  start: BaseNode,
  llm: BaseNode,
  tool: BaseNode,
  code: BaseNode,
  condition: BaseNode,
  loop: BaseNode,
  web_search: BaseNode,
  knowledge: BaseNode,
  http_request: BaseNode,
  input: BaseNode,
  aggregator: BaseNode,
  variable: BaseNode,
  end: BaseNode,
}

// --------------------------------------------------------------------------- #
// Main editor
// --------------------------------------------------------------------------- #

interface WorkflowEditorProps {
  workflowId: string | null
  workflowName: string
  initialNodes: Node[]
  initialEdges: Edge[]
  onSave: (nodes: Node[], edges: Edge[]) => Promise<void>
  onRun: () => Promise<void>
  isRunning: boolean
  currentNodeId: string | null
  onBack: () => void
}

export function WorkflowEditor({
  workflowName,
  initialNodes,
  initialEdges,
  onSave,
  onRun,
  isRunning,
  currentNodeId,
  onBack,
}: WorkflowEditorProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [nodeTypes, setNodeTypes] = useState<NodeTypeMeta[]>([])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>(
    'idle'
  )

  useEffect(() => {
    listNodeTypes().then(setNodeTypes).catch(() => setNodeTypes([]))
  }, [])

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge({ ...params, id: `e-${Date.now()}` }, eds)),
    [setEdges]
  )

  const addNode = (type: string) => {
    const id = `n-${type}-${Date.now()}`
    setNodes((nds) => [
      ...nds,
      {
        id,
        type,
        position: {
          x: 100 + Math.random() * 200,
          y: 100 + Math.random() * 200,
        },
        data: { label: type, type, prompt: '', system: '' } as NodeData,
      },
    ])
  }

  const handleSave = async () => {
    setSaveStatus('saving')
    try {
      await onSave(nodes, edges)
      setSaveStatus('saved')
      setTimeout(() => setSaveStatus('idle'), 2000)
    } catch {
      setSaveStatus('error')
    }
  }

  const selectedNode = nodes.find((n) => n.id === selectedNodeId)
  const currentNode = currentNodeId
    ? nodes.find((n) => n.id === currentNodeId)
    : null

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '8px 16px',
          borderBottom: '1px solid var(--color-border)',
          background: 'var(--color-surface-container-low)',
          gap: 8,
        }}
      >
        <button
          onClick={onBack}
          style={{
            padding: '4px 10px',
            background: 'transparent',
            border: '1px solid var(--color-border)',
            borderRadius: 4,
            color: 'var(--color-text-primary)',
            cursor: 'pointer',
          }}
        >
          ← 返回
        </button>
        <h2
          style={{
            margin: 0,
            fontSize: 16,
            fontWeight: 600,
            flex: 1,
            color: 'var(--color-text-primary)',
          }}
        >
          {workflowName || '新工作流'}
        </h2>
        <button
          onClick={handleSave}
          disabled={isRunning}
          style={{
            padding: '6px 14px',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: 4,
            color: 'var(--color-text-primary)',
            cursor: 'pointer',
            fontWeight: 500,
          }}
        >
          {saveStatus === 'saving' ? '保存中…' : saveStatus === 'saved' ? '✓ 已保存' : '保存'}
        </button>
        <button
          onClick={onRun}
          disabled={isRunning}
          style={{
            padding: '6px 14px',
            background: isRunning
              ? 'var(--color-surface-container-high)'
              : 'var(--color-brand)',
            border: 'none',
            borderRadius: 4,
            color: '#fff',
            cursor: isRunning ? 'default' : 'pointer',
            fontWeight: 600,
          }}
        >
          {isRunning ? '运行中…' : '▶ 运行'}
        </button>
      </div>

      {/* Main area: sidebar + canvas + config panel */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/* Left: node library */}
        <div
          style={{
            width: 160,
            background: 'var(--color-surface-container-lowest)',
            borderRight: '1px solid var(--color-border)',
            padding: 12,
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}
        >
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: 1,
              color: 'var(--color-text-tertiary)',
            }}
          >
            节点库
          </div>
          {nodeTypes.map((nt) => (
            <button
              key={nt.type}
              onClick={() => addNode(nt.type)}
              disabled={isRunning}
              style={{
                padding: '8px 12px',
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: 4,
                color: 'var(--color-text-primary)',
                cursor: 'pointer',
                textAlign: 'left',
                fontSize: 13,
              }}
              title={nt.description}
            >
              {nt.label}
            </button>
          ))}
        </div>

        {/* Middle: canvas */}
        <div style={{ flex: 1, position: 'relative' }} data-testid="workflow-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, n) => setSelectedNodeId(n.id)}
            onPaneClick={() => setSelectedNodeId(null)}
            nodeTypes={NODE_TYPE_REGISTRY}
            fitView
            proOptions={{ hideAttribution: true }}
            nodesDraggable={!isRunning}
            nodesConnectable={!isRunning}
            elementsSelectable={!isRunning}
          >
            <Background gap={20} size={1} />
            <Controls />
            <MiniMap />
          </ReactFlow>
          {currentNode && (
            <div
              style={{
                position: 'absolute',
                top: 16,
                right: 16,
                background: 'var(--color-brand)',
                color: '#fff',
                padding: '6px 12px',
                borderRadius: 4,
                fontSize: 12,
                fontWeight: 500,
                boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
              }}
            >
              正在运行: {currentNode.data?.label as string || currentNode.id}
            </div>
          )}
        </div>

        {/* Right: node config panel */}
        {selectedNode && (
          <div
            style={{
              width: 320,
              background: 'var(--color-surface-container-lowest)',
              borderLeft: '1px solid var(--color-border)',
              padding: 16,
              overflowY: 'auto',
            }}
          >
            <div
              style={{
                fontSize: 11,
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: 1,
                color: 'var(--color-text-tertiary)',
                marginBottom: 8,
              }}
            >
              节点配置
            </div>
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: 'var(--color-text-primary)',
                marginBottom: 12,
              }}
            >
              {(selectedNode.data?.label as string) || selectedNode.id} ({selectedNode.type})
            </div>

            {selectedNode.type === 'llm' && (
              <>
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--color-text-secondary)' }}>
                  节点标签
                </label>
                <input
                  type="text"
                  value={(selectedNode.data?.label as string) || ''}
                  onChange={(e) => {
                    setNodes((nds) =>
                      nds.map((n) =>
                        n.id === selectedNode.id
                          ? { ...n, data: { ...n.data, label: e.target.value } }
                          : n
                      )
                    )
                  }}
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    border: '1px solid var(--color-border)',
                    borderRadius: 4,
                    background: 'var(--color-surface)',
                    color: 'var(--color-text-primary)',
                    marginBottom: 12,
                    fontSize: 13,
                  }}
                />
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--color-text-secondary)' }}>
                  System Prompt (可选)
                </label>
                <textarea
                  value={(selectedNode.data?.system as string) || ''}
                  onChange={(e) => {
                    setNodes((nds) =>
                      nds.map((n) =>
                        n.id === selectedNode.id
                          ? { ...n, data: { ...n.data, system: e.target.value } }
                          : n
                      )
                    )
                  }}
                  rows={3}
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    border: '1px solid var(--color-border)',
                    borderRadius: 4,
                    background: 'var(--color-surface)',
                    color: 'var(--color-text-primary)',
                    marginBottom: 12,
                    fontSize: 13,
                    fontFamily: 'inherit',
                    resize: 'vertical',
                  }}
                />
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--color-text-secondary)' }}>
                  User Prompt (支持 {'{{input}}'}{' / '}{'{{node_id}}'}{' / '}{'{{node_id.output}}'}{')'}
                </label>
                <textarea
                  value={(selectedNode.data?.prompt as string) || ''}
                  onChange={(e) => {
                    setNodes((nds) =>
                      nds.map((n) =>
                        n.id === selectedNode.id
                          ? { ...n, data: { ...n.data, prompt: e.target.value } }
                          : n
                      )
                    )
                  }}
                  rows={6}
                  placeholder="用一句话回答: {{input}}"
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    border: '1px solid var(--color-border)',
                    borderRadius: 4,
                    background: 'var(--color-surface)',
                    color: 'var(--color-text-primary)',
                    fontSize: 13,
                    fontFamily: 'var(--font-mono, monospace)',
                    resize: 'vertical',
                  }}
                />
              </>
            )}

            {selectedNode.type === 'tool' && (
              <>
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--color-text-secondary)' }}>
                  节点标签
                </label>
                <input
                  type="text"
                  value={(selectedNode.data?.label as string) || ''}
                  onChange={(e) => {
                    setNodes((nds) =>
                      nds.map((n) =>
                        n.id === selectedNode.id
                          ? { ...n, data: { ...n.data, label: e.target.value } }
                          : n
                      )
                    )
                  }}
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    border: '1px solid var(--color-border)',
                    borderRadius: 4,
                    background: 'var(--color-surface)',
                    color: 'var(--color-text-primary)',
                    marginBottom: 12,
                    fontSize: 13,
                  }}
                />
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--color-text-secondary)' }}>
                  工具名
                </label>
                <input
                  type="text"
                  value={(selectedNode.data?.tool as string) || ''}
                  onChange={(e) => {
                    setNodes((nds) =>
                      nds.map((n) =>
                        n.id === selectedNode.id
                          ? { ...n, data: { ...n.data, tool: e.target.value } }
                          : n
                      )
                    )
                  }}
                  placeholder="get_weather"
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    border: '1px solid var(--color-border)',
                    borderRadius: 4,
                    background: 'var(--color-surface)',
                    color: 'var(--color-text-primary)',
                    marginBottom: 12,
                    fontSize: 13,
                  }}
                />
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--color-text-secondary)' }}>
                  参数 (JSON, 支持 {'{{input}}'})
                </label>
                <textarea
                  value={(selectedNode.data?.params ? JSON.stringify(selectedNode.data.params, null, 2) : '') || ''}
                  onChange={(e) => {
                    try {
                      const parsed = JSON.parse(e.target.value)
                      setNodes((nds) =>
                        nds.map((n) =>
                          n.id === selectedNode.id
                            ? { ...n, data: { ...n.data, params: parsed } }
                            : n
                        )
                      )
                    } catch {
                      // Allow typing invalid JSON — stored as raw string
                    }
                  }}
                  rows={5}
                  placeholder='{"city": "Hangzhou"}'
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    border: '1px solid var(--color-border)',
                    borderRadius: 4,
                    background: 'var(--color-surface)',
                    color: 'var(--color-text-primary)',
                    fontSize: 13,
                    fontFamily: 'var(--font-mono, monospace)',
                    resize: 'vertical',
                  }}
                />
              </>
            )}

            {/* Generic JSON config for any node type without a specific panel */}
            {selectedNode.type !== 'llm' && selectedNode.type !== 'tool' && selectedNode.type !== 'start' && selectedNode.type !== 'end' && (
              <>
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--color-text-secondary)' }}>
                  节点标签
                </label>
                <input
                  type="text"
                  value={(selectedNode.data?.label as string) || ''}
                  onChange={(e) => {
                    setNodes((nds) =>
                      nds.map((n) =>
                        n.id === selectedNode.id
                          ? { ...n, data: { ...n.data, label: e.target.value } }
                          : n
                      )
                    )
                  }}
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    border: '1px solid var(--color-border)',
                    borderRadius: 4,
                    background: 'var(--color-surface)',
                    color: 'var(--color-text-primary)',
                    marginBottom: 12,
                    fontSize: 13,
                  }}
                />
                <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--color-text-secondary)' }}>
                  配置 (JSON, 支持 {'{{input}}'})
                </label>
                <textarea
                  value={JSON.stringify(
                    Object.fromEntries(
                      Object.entries(selectedNode.data || {}).filter(([k]) => k !== 'label')
                    ),
                    null, 2
                  ) || '{}'}
                  onChange={(e) => {
                    try {
                      const parsed = JSON.parse(e.target.value)
                      setNodes((nds) =>
                        nds.map((n) =>
                          n.id === selectedNode.id
                            ? { ...n, data: { ...n.data, ...parsed } }
                            : n
                        )
                      )
                    } catch {
                      // Allow typing invalid JSON
                    }
                  }}
                  rows={8}
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    border: '1px solid var(--color-border)',
                    borderRadius: 4,
                    background: 'var(--color-surface)',
                    color: 'var(--color-text-primary)',
                    fontSize: 13,
                    fontFamily: 'var(--font-mono, monospace)',
                    resize: 'vertical',
                  }}
                />
              </>
            )}

            <button
              onClick={() => {
                setNodes((nds) => nds.filter((n) => n.id !== selectedNode.id))
                setEdges((eds) => eds.filter((e) => e.source !== selectedNode.id && e.target !== selectedNode.id))
                setSelectedNodeId(null)
              }}
              disabled={isRunning}
              style={{
                marginTop: 16,
                padding: '6px 12px',
                background: 'transparent',
                border: '1px solid #ef4444',
                color: '#ef4444',
                borderRadius: 4,
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              删除节点
            </button>
          </div>
        )}
      </div>
    </div>
  )
}