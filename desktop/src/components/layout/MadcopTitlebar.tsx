// v3.0 — MadCop title bar.
//
// The previous TitleBar dragged a 40px row with traffic-light
// buttons on the right and a "New Project" menu. The new one is
// flatter: 32px, a small left-side wordmark, a center command input
// (jump-to / command-palette later), and macOS window controls on
// the right (kept the same for now).

import { useState } from 'react'
import { madcop, icon } from '../../foundations/tokens'

interface MadcopTitlebarProps {
  projectName?: string
  onCommand?: (cmd: string) => void
}

export function MadcopTitlebar({ projectName, onCommand }: MadcopTitlebarProps) {
  const [cmd, setCmd] = useState('')

  return (
    <div style={{
      width: '100%', height: '100%',
      display: 'flex', alignItems: 'center',
      padding: `0 ${madcop.space[3]}`,
      gap: madcop.space[3],
      background: 'var(--madcop-panel-raised)',
      WebkitAppRegion: 'drag',
    } as React.CSSProperties}>
      {/* Left: project + breadcrumb */}
      <div style={{ display: 'flex', alignItems: 'center', gap: madcop.space[2], minWidth: 200 }}>
        <span style={{
          fontFamily: madcop.type.family.mono, fontSize: 11, color: 'var(--madcop-ink-muted)',
          letterSpacing: madcop.type.tracking.wide,
        }}>MADCOP</span>
        {projectName && (
          <>
            <span style={{ color: 'var(--madcop-line)' }}>/</span>
            <span style={{ fontSize: madcop.type.size.body, color: 'var(--madcop-ink)' }}>{projectName}</span>
          </>
        )}
      </div>

      {/* Center: command input */}
      <div style={{
        flex: 1, display: 'flex', justifyContent: 'center',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: madcop.space[2],
          width: 320, padding: `4px 10px`,
          border: `1.5px solid var(--madcop-line)`,
          background: 'var(--madcop-panel-sunken)',
        }}>
          <span style={{ color: 'var(--madcop-ink-muted)', fontFamily: madcop.type.family.mono, fontSize: 12 }}>{icon.find}</span>
          <input
            value={cmd}
            onChange={(e) => setCmd(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && cmd.trim()) {
                onCommand?.(cmd.trim())
                setCmd('')
              }
            }}
            placeholder="执行命令 — 选模型、写提示、跳转"
            style={{
              flex: 1, border: 'none', outline: 'none', background: 'transparent',
              fontSize: madcop.type.size.body, color: 'var(--madcop-ink)',
              fontFamily: madcop.type.family.ui,
            }}
          />
          <kbd style={{
            fontSize: 10, color: 'var(--madcop-ink-muted)',
            border: `1px solid var(--madcop-line)`, padding: '1px 4px',
            fontFamily: madcop.type.family.mono,
          }}>⌘K</kbd>
        </div>
      </div>

      {/* Right: window controls (macOS — handled by TitleBar) */}
      <div style={{ minWidth: 200, display: 'flex', justifyContent: 'flex-end', gap: madcop.space[2] }}>
        <button
          onClick={() => onCommand?.('appearance:toggle')}
          title="切换主题"
          style={{
            padding: '4px 10px', border: `1.5px solid var(--madcop-line)`,
            background: 'var(--madcop-panel-raised)', color: 'var(--madcop-ink-muted)',
            fontSize: 11, fontFamily: madcop.type.family.mono, cursor: 'pointer',
          }}
        >
          主题
        </button>
        <button
          onClick={() => onCommand?.('settings:open')}
          title="设置"
          style={{
            padding: '4px 10px', border: `1.5px solid var(--madcop-line)`,
            background: 'var(--madcop-panel-raised)', color: 'var(--madcop-ink-muted)',
            fontSize: 11, fontFamily: madcop.type.family.mono, cursor: 'pointer',
          }}
        >
          设置
        </button>
      </div>
    </div>
  )
}
