// v3.0 — MadCop settings page.
//
// Replaces the old Settings.tsx. The new page is a single column
// of sectioned accordions, each section has a title in eyebrow
// style and rows with label + control. No animated preview cards,
// no left-side mini-nav, no three-pane iframe shell.

import { useState, useEffect } from 'react'
import { madcop, icon } from '../foundations/tokens'
import { useMadcopTheme, type MadcopAppearance } from '../foundations/theme'
import { getApiUrl } from '../api/client'

interface ProviderItem {
  id: string
  name: string
  base_url: string
  model: string
  has_key: boolean
}

export function MadcopSettings() {
  const { appearance, setAppearance } = useMadcopTheme()
  const [providers, setProviders] = useState<ProviderItem[]>([])
  const [activeProvider, setActiveProvider] = useState<string | null>(null)
  const [activeModel, setActiveModel] = useState<string>('')

  useEffect(() => {
    fetch(getApiUrl('/api/settings')).then((r) => r.json()).then((s) => {
      setProviders(Object.values(s.providers || {}) as any)
      setActiveProvider(s.active_provider)
    }).catch(() => {})
  }, [])

  return (
    <div style={{
      width: '100%', height: '100%',
      overflowY: 'auto', background: 'var(--madcop-panel)',
    }}>
      <div style={{ maxWidth: 720, margin: '0 auto', padding: madcop.space[8] }}>
        <h1 style={{
          margin: `0 0 ${madcop.space[6]}`,
          fontSize: madcop.type.size.h1, fontWeight: 600,
          letterSpacing: madcop.type.tracking.tight, color: 'var(--madcop-ink)',
        }}>设置</h1>

        {/* ── 主题 ── */}
        <Section title="外观">
          <Row label="主题" hint="亮色 / 暗色 / 牛皮纸">
            <div style={{ display: 'flex', gap: madcop.space[2] }}>
              {(['light', 'dark', 'sepia'] as const).map((a) => (
                <button
                  key={a}
                  onClick={() => setAppearance(a)}
                  style={{
                    padding: `6px 14px`, border: `1.5px solid`,
                    borderColor: appearance === a ? 'var(--madcop-accent)' : 'var(--madcop-line)',
                    background: appearance === a ? 'var(--madcop-accent-subtle)' : 'var(--madcop-panel-raised)',
                    color: appearance === a ? 'var(--madcop-accent)' : 'var(--madcop-ink-body)',
                    fontSize: madcop.type.size.body, cursor: 'pointer',
                  }}
                >
                  {a === 'light' ? '亮色' : a === 'dark' ? '暗色' : '牛皮纸'}
                </button>
              ))}
            </div>
          </Row>
          <Row label="网格背景" hint="细微的工程蓝图网格">
            <Toggle defaultOn />
          </Row>
          <Row label="等宽数字" hint="表格、计数器使用等宽字体">
            <Toggle defaultOn />
          </Row>
        </Section>

        {/* ── 模型 ── */}
        <Section title="模型">
          <Row label="当前供应商" hint="点击切换激活的 provider">
            <select
              value={activeProvider || ''}
              onChange={(e) => setActiveProvider(e.target.value)}
              style={selectStyle}
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} {p.has_key ? '' : '(无 API key)'}
                </option>
              ))}
            </select>
          </Row>
          <Row label="当前模型">
            <input
              type="text"
              value={activeModel}
              onChange={(e) => setActiveModel(e.target.value)}
              placeholder="glm-5.2"
              style={inputStyle}
            />
          </Row>
        </Section>

        {/* ── 快捷键 ── */}
        <Section title="快捷键">
          <Row label="命令面板" hint="跳转到任意面板或执行命令">
            <Kbd>⌘K</Kbd>
          </Row>
          <Row label="新建会话">
            <Kbd>⌘N</Kbd>
          </Row>
          <Row label="切换主题">
            <Kbd>⌘⇧L</Kbd>
          </Row>
        </Section>

        {/* ── 关于 ── */}
        <Section title="关于">
          <Row label="版本">
            <span style={{ color: 'var(--madcop-ink-muted)', fontFamily: madcop.type.family.mono, fontSize: madcop.type.size.body }}>v3.0.0</span>
          </Row>
          <Row label="LLM 客户端">
            <span style={{ color: 'var(--madcop-ink-muted)', fontFamily: madcop.type.family.mono, fontSize: madcop.type.size.body }}>OpenAI 兼容 · 4 个 provider</span>
          </Row>
          <Row label="可视化编辑器">
            <span style={{ color: 'var(--madcop-ink-muted)', fontFamily: madcop.type.family.mono, fontSize: madcop.type.size.body }}>原生 HTML5 · 0 依赖</span>
          </Row>
        </Section>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: madcop.space[8] }}>
      <div className="madcop-eyebrow" style={{ marginBottom: madcop.space[3] }}>{title}</div>
      <div style={{
        border: `1.5px solid var(--madcop-line)`,
        background: 'var(--madcop-panel-raised)',
      }}>
        {children}
      </div>
    </div>
  )
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '180px 1fr',
      alignItems: 'center', gap: madcop.space[4],
      padding: `${madcop.space[3]} ${madcop.space[4]}`,
      borderBottom: `1px solid var(--madcop-line)`,
    }}>
      <div>
        <div style={{ fontSize: madcop.type.size.body, fontWeight: 500, color: 'var(--madcop-ink)' }}>{label}</div>
        {hint && <div style={{ fontSize: madcop.type.size.micro, color: 'var(--madcop-ink-muted)', marginTop: 2 }}>{hint}</div>}
      </div>
      <div>{children}</div>
    </div>
  )
}

function Toggle({ defaultOn }: { defaultOn?: boolean }) {
  const [on, setOn] = useState(!!defaultOn)
  return (
    <button
      onClick={() => setOn(!on)}
      style={{
        width: 40, height: 22, padding: 2,
        background: on ? 'var(--madcop-accent)' : 'var(--madcop-line)',
        border: 'none', cursor: 'pointer', position: 'relative',
        transition: 'background 140ms',
      }}
    >
      <span style={{
        display: 'block', width: 18, height: 18,
        background: 'var(--madcop-ink-invert)',
        transform: on ? 'translateX(18px)' : 'translateX(0)',
        transition: 'transform 140ms',
      }} />
    </button>
  )
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd style={{
      display: 'inline-block',
      padding: '4px 8px', minWidth: 28, textAlign: 'center',
      border: `1.5px solid var(--madcop-line)`,
      background: 'var(--madcop-panel-sunken)',
      color: 'var(--madcop-ink-body)',
      fontSize: madcop.type.size.micro, fontFamily: madcop.type.family.mono,
    }}>{children}</kbd>
  )
}

const inputStyle: React.CSSProperties = {
  padding: `6px 10px`,
  border: `1.5px solid var(--madcop-line)`,
  background: 'var(--madcop-panel-sunken)',
  fontSize: madcop.type.size.body,
  color: 'var(--madcop-ink)',
  fontFamily: madcop.type.family.ui,
  outline: 'none',
}

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  cursor: 'pointer',
}
