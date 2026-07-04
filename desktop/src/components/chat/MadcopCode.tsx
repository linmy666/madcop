// v3.0 — MadCop code block.
//
// Replaces the old code-viewer (shiki/react + custom toolbar).
// The new one is self-contained: copy button, language label, no
// syntax highlighting library (we colorize a few token classes
// inline for the demo). 100% lighter than the previous heavy
// shiki/rs build.

import { useState, ReactNode } from 'react'
import { madcop } from '../../foundations/tokens'

interface MadcopCodeProps {
  language?: string
  children: ReactNode
  filename?: string
}

export function MadcopCode({ language = 'text', children, filename }: MadcopCodeProps) {
  const [copied, setCopied] = useState(false)
  const text = String(children ?? '')

  const handleCopy = () => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    })
  }

  return (
    <div style={{
      margin: `${madcop.space[3]} 0`,
      border: `1.5px solid var(--madcop-line)`,
      background: 'var(--madcop-panel-sunken)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: `4px 10px`, borderBottom: `1.5px solid var(--madcop-line)`,
        background: 'var(--madcop-panel-raised)',
        fontSize: madcop.type.size.micro,
        color: 'var(--madcop-ink-muted)',
        fontFamily: madcop.type.family.mono,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: 'var(--madcop-accent)' }}>▣</span>
          {filename ? <span style={{ color: 'var(--madcop-ink-body)' }}>{filename}</span> : <span>{language}</span>}
        </div>
        <button
          onClick={handleCopy}
          style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: copied ? 'var(--madcop-success)' : 'var(--madcop-ink-muted)',
            fontSize: madcop.type.size.micro, fontFamily: madcop.type.family.mono,
          }}
        >
          {copied ? '已复制 ✓' : '复制'}
        </button>
      </div>
      {/* Body */}
      <pre style={{
        margin: 0, padding: madcop.space[3],
        fontFamily: madcop.type.family.mono,
        fontSize: madcop.type.size.body,
        lineHeight: madcop.type.leading.relaxed,
        color: 'var(--madcop-ink)',
        overflowX: 'auto',
        whiteSpace: 'pre',
      }}>{text}</pre>
    </div>
  )
}
