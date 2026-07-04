// v3.0 — MadCop assistant message.
//
// Self-contained: header with role + model + copy, body that
// gracefully degrades from a markdown string to a list of block
// types. No markdown library; we recognize a few inline tokens
// (code spans, bold, italic) via regex.

import { useState } from 'react'
import { madcop, icon } from '../../foundations/tokens'
import { MadcopCode } from './MadcopCode'

interface MadcopMessageProps {
  role: 'assistant' | 'user' | 'system' | 'tool'
  author: string
  content: string
  model?: string
  thinking?: string
  toolCalls?: Array<{ name: string; status: 'pending' | 'ok' | 'error'; detail?: string }>
  timestamp?: number
}

export function MadcopMessage({ role, author, content, model, thinking, toolCalls, timestamp }: MadcopMessageProps) {
  const [showThinking, setShowThinking] = useState(false)
  const [copied, setCopied] = useState(false)

  const roleColor = role === 'user'
    ? 'var(--madcop-warn)'
    : role === 'tool'
    ? 'var(--madcop-success)'
    : 'var(--madcop-accent)'

  const roleLabel = role === 'user' ? 'USER' : role === 'tool' ? 'TOOL' : role === 'system' ? 'SYS' : 'ASSIST'

  const handleCopy = () => {
    navigator.clipboard?.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1400)
  }

  return (
    <div style={{
      padding: `${madcop.space[4]} ${madcop.space[5]}`,
      borderBottom: `1.5px solid var(--madcop-line)`,
      background: 'var(--madcop-panel)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: madcop.space[3],
        marginBottom: madcop.space[3],
        fontSize: madcop.type.size.micro, fontFamily: madcop.type.family.mono,
        color: 'var(--madcop-ink-muted)',
      }}>
        <span style={{
          padding: '2px 6px',
          background: roleColor, color: 'var(--madcop-ink-invert)',
          fontSize: 10, fontWeight: 700, letterSpacing: madcop.type.tracking.wide,
        }}>{roleLabel}</span>
        <span style={{ color: 'var(--madcop-ink)', fontFamily: madcop.type.family.ui, fontWeight: 500, fontSize: madcop.type.size.body }}>{author}</span>
        {model && <span style={{ color: 'var(--madcop-ink-subtle)' }}>· {model}</span>}
        <div style={{ flex: 1 }} />
        {timestamp && <span>{new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</span>}
        <button onClick={handleCopy} style={{
          background: 'transparent', border: 'none', cursor: 'pointer',
          color: copied ? 'var(--madcop-success)' : 'var(--madcop-ink-muted)',
          fontSize: madcop.type.size.micro, fontFamily: madcop.type.family.mono,
        }}>{copied ? '已复制 ✓' : '复制'}</button>
      </div>

      {/* Thinking block */}
      {thinking && (
        <div style={{ marginBottom: madcop.space[3] }}>
          <button
            onClick={() => setShowThinking(!showThinking)}
            style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: 'var(--madcop-ink-muted)', fontSize: madcop.type.size.micro,
              fontFamily: madcop.type.family.mono, padding: 0,
            }}
          >
            {showThinking ? '▾' : '▸'} 思考过程
          </button>
          {showThinking && (
            <div style={{
              marginTop: 6, padding: madcop.space[3],
              background: 'var(--madcop-panel-sunken)',
              borderLeft: `3px solid var(--madcop-warn)`,
              fontSize: madcop.type.size.body, color: 'var(--madcop-ink-body)',
              fontFamily: madcop.type.family.mono, whiteSpace: 'pre-wrap',
            }}>{thinking}</div>
          )}
        </div>
      )}

      {/* Body */}
      <div style={{
        color: 'var(--madcop-ink)', fontSize: madcop.type.size.base,
        lineHeight: madcop.type.leading.relaxed,
      }}>
        <MessageBody content={content} />
      </div>

      {/* Tool calls */}
      {toolCalls && toolCalls.length > 0 && (
        <div style={{
          marginTop: madcop.space[3],
          border: `1.5px solid var(--madcop-line)`,
          background: 'var(--madcop-panel-sunken)',
        }}>
          {toolCalls.map((tc, i) => {
            const statusGlyph = tc.status === 'ok' ? '✓' : tc.status === 'error' ? '✕' : '⋯'
            const statusColor = tc.status === 'ok'
              ? 'var(--madcop-success)'
              : tc.status === 'error'
              ? 'var(--madcop-danger)'
              : 'var(--madcop-warn)'
            return (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: madcop.space[2],
                padding: `4px 10px`,
                borderBottom: i < toolCalls.length - 1 ? `1px solid var(--madcop-line)` : 'none',
                fontSize: madcop.type.size.micro, fontFamily: madcop.type.family.mono,
                color: 'var(--madcop-ink-muted)',
              }}>
                <span style={{ color: statusColor }}>{statusGlyph}</span>
                <span style={{ color: 'var(--madcop-ink-body)' }}>{tc.name}</span>
                {tc.detail && <span style={{ color: 'var(--madcop-ink-subtle)' }}>— {tc.detail}</span>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function MessageBody({ content }: { content: string }) {
  // Split by code fences first
  const parts = content.split(/(```[\s\S]*?```)/g)
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('```')) {
          const m = part.match(/^```(\w+)?\n?([\s\S]*?)\n?```$/)
          if (m) return <MadcopCode key={i} language={m[1] || 'text'}>{m[2]}</MadcopCode>
          return <pre key={i} className="madcop-code">{part.slice(3, -3)}</pre>
        }
        // Paragraphs
        return part.split(/\n\n+/).map((p, j) => (
          <p key={`${i}-${j}`} style={{ margin: `${madcop.space[2]} 0` }}>
            {renderInline(p)}
          </p>
        ))
      })}
    </>
  )
}

function renderInline(text: string): React.ReactNode[] {
  // Process: `code`, **bold**, *italic*
  const tokens: React.ReactNode[] = []
  const regex = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)/g
  let lastIdx = 0
  let m: RegExpExecArray | null
  let key = 0
  while ((m = regex.exec(text)) !== null) {
    if (m.index > lastIdx) tokens.push(text.slice(lastIdx, m.index))
    if (m[1]) tokens.push(<code key={key++} style={{ background: 'var(--madcop-panel-sunken)', padding: '1px 4px', fontFamily: madcop.type.family.mono, fontSize: '0.92em' }}>{m[1].slice(1, -1)}</code>)
    else if (m[2]) tokens.push(<strong key={key++}>{m[2].slice(2, -2)}</strong>)
    else if (m[3]) tokens.push(<em key={key++}>{m[3].slice(1, -1)}</em>)
    lastIdx = regex.lastIndex
  }
  if (lastIdx < text.length) tokens.push(text.slice(lastIdx))
  return tokens
}
