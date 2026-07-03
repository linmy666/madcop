// v2.8.0 — ModeSelector: dropdown for choosing Agent design pattern.
// Shows 12 Google Cloud patterns. Default is "react" (ReAct).
import { useEffect, useRef, useState } from 'react'
import { getApiUrl } from '../../api/client'

export interface AgentMode {
  id: string
  name: string
  description: string
  category: string
  icon: string
  node_count: number
}

interface Props {
  currentMode: string
  onModeChange: (modeId: string) => void
}

export function ModeSelector({ currentMode, onModeChange }: Props) {
  const [modes, setModes] = useState<AgentMode[]>([])
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getApiUrl('/api/workflows/modes')
    fetch(getApiUrl('/api/workflows/modes'))
      .then((r) => r.json())
      .then((d) => setModes(d.modes || []))
      .catch(() => {
        // Fallback if API not available
        setModes([
          { id: 'react', name: 'ReAct 推理', description: '默认模式', category: 'basic', icon: '🧠', node_count: 2 },
        ])
      })
  }, [])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const current = modes.find((m) => m.id === currentMode)
  const categories = ['basic', 'multi_agent', 'advanced']
  const categoryLabels: Record<string, string> = {
    basic: '基础',
    multi_agent: '多 Agent',
    advanced: '高级',
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          padding: '4px 8px',
          background: 'transparent',
          border: '1px solid var(--color-border)',
          borderRadius: 4,
          color: 'var(--color-text-secondary)',
          fontSize: 12,
          cursor: 'pointer',
          whiteSpace: 'nowrap',
        }}
        title={current?.description || '选择模式'}
      >
        <span>{current?.icon || '🧠'}</span>
        <span>{current?.name || 'ReAct'}</span>
        <span style={{ fontSize: 9, opacity: 0.6 }}>▾</span>
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            bottom: '100%',
            left: 0,
            marginBottom: 4,
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: 8,
            boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
            maxHeight: 400,
            overflowY: 'auto',
            minWidth: 280,
            zIndex: 100,
          }}
        >
          {categories.map((cat) => (
            <div key={cat}>
              <div
                style={{
                  padding: '6px 12px',
                  fontSize: 10,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: 1,
                  color: 'var(--color-text-tertiary)',
                  borderBottom: '1px solid var(--color-border)',
                }}
              >
                {categoryLabels[cat]}
              </div>
              {modes
                .filter((m) => m.category === cat)
                .map((m) => (
                  <button
                    key={m.id}
                    onClick={() => {
                      onModeChange(m.id)
                      setOpen(false)
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 8,
                      padding: '8px 12px',
                      width: '100%',
                      background:
                        m.id === currentMode
                          ? 'var(--color-surface-hover)'
                          : 'transparent',
                      border: 'none',
                      borderBottom: '1px solid var(--color-border)',
                      color: 'var(--color-text-primary)',
                      cursor: 'pointer',
                      textAlign: 'left',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'var(--color-surface-hover)'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background =
                        m.id === currentMode
                          ? 'var(--color-surface-hover)'
                          : 'transparent'
                    }}
                  >
                    <span style={{ fontSize: 16, flexShrink: 0 }}>{m.icon}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{m.name}</div>
                      <div
                        style={{
                          fontSize: 11,
                          color: 'var(--color-text-tertiary)',
                          whiteSpace: 'normal',
                        }}
                      >
                        {m.description}
                      </div>
                    </div>
                    {m.id === currentMode && (
                      <span style={{ fontSize: 14, color: 'var(--color-brand)' }}>✓</span>
                    )}
                  </button>
                ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}