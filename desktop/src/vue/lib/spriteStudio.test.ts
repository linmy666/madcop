import { describe, expect, it, beforeEach } from 'vitest'
import {
  buildSpriteRoster,
  selectSpriteDetail,
  poseFromToolName,
  inferRole,
  loadStudioSkin,
  saveStudioSkin,
  loadIslandEnabled,
  saveIslandEnabled,
  SKIN_STORAGE_KEY,
  ISLAND_ENABLED_KEY,
} from './spriteStudio'

describe('inferRole / poseFromToolName', () => {
  it('infers specialist roles from ids and names', () => {
    expect(inferRole('planner', '规划')).toBe('planner')
    expect(inferRole('coder-1', '写码助手')).toBe('coder')
    expect(inferRole('x', 'UI 设计')).toBe('designer')
    expect(inferRole('researcher', '')).toBe('researcher')
  })

  it('maps tool names to tool poses', () => {
    expect(poseFromToolName('write_file')).toBe('tool_file')
    expect(poseFromToolName('web_search')).toBe('tool_web')
    expect(poseFromToolName('unknown_tool')).toBe('working')
    expect(poseFromToolName(null)).toBeNull()
  })
})

describe('buildSpriteRoster', () => {
  it('maps running stream → thinking/working', () => {
    const roster = buildSpriteRoster({
      agentStreams: {
        planner: { name: '规划', color: '#7C3AED', text: '', status: 'running' },
        coder: { name: '写码', color: '#2563EB', text: 'def foo():', status: 'running' },
      },
    })
    expect(roster).toHaveLength(2)
    const p = roster.find((r) => r.id === 'planner')!
    const c = roster.find((r) => r.id === 'coder')!
    expect(p.pose).toBe('thinking')
    expect(c.pose).toBe('working')
    expect(c.text).toContain('def foo')
  })

  it('maps done → done and error → error', () => {
    const roster = buildSpriteRoster({
      agentStreams: {
        a: { name: 'A', color: '#111', text: 'ok', status: 'done' },
        b: { name: 'B', color: '#222', text: 'fail', status: 'error' },
      },
    })
    expect(roster.find((r) => r.id === 'a')!.pose).toBe('done')
    expect(roster.find((r) => r.id === 'b')!.pose).toBe('error')
  })

  it('maps clarification → blocked on running agents', () => {
    const roster = buildSpriteRoster({
      agentStreams: {
        main: { name: '助手', color: '#7C3AED', text: '?', status: 'running' },
      },
      clarificationPending: { question: '选哪个方案？', options: ['A', 'B'] },
    })
    expect(roster[0].pose).toBe('blocked')
    expect(roster[0].bubble).toContain('方案')
  })

  it('uses activeToolName for tool-adjacent poses', () => {
    const roster = buildSpriteRoster({
      agentStreams: {
        c: { name: '写码', color: '#2563EB', text: '…', status: 'running' },
      },
      activeToolName: 'read_file',
    })
    expect(roster[0].pose).toBe('tool_file')
  })

  it('falls back to deepRoute specialists when no streams', () => {
    const roster = buildSpriteRoster({
      deepRoute: {
        category: 'coding',
        specialists: ['planner', 'coder', 'reviewer'],
        label_zh: '编码',
        label_en: 'coding',
      },
      chatState: 'streaming',
    })
    expect(roster.length).toBe(3)
    expect(roster.map((r) => r.role)).toEqual(
      expect.arrayContaining(['planner', 'coder', 'reviewer']),
    )
    expect(roster.some((r) => r.pose === 'thinking' || r.pose === 'idle')).toBe(true)
  })

  it('returns empty roster when fully idle', () => {
    expect(buildSpriteRoster({ chatState: 'idle' })).toEqual([])
    expect(buildSpriteRoster({})).toEqual([])
  })

  it('solo calm sprite when busy without multi-agent', () => {
    const roster = buildSpriteRoster({ chatState: 'streaming', activeToolName: 'web_fetch' })
    expect(roster).toHaveLength(1)
    expect(roster[0].id).toBe('main')
    expect(roster[0].pose).toBe('tool_web')
  })
})

describe('selectSpriteDetail', () => {
  it('returns A’s payload from the real roster helper', () => {
    const roster = buildSpriteRoster({
      agentStreams: {
        a: { name: '规划', color: '#7C3AED', text: '先拆步骤', status: 'running' },
        b: { name: '写码', color: '#2563EB', text: 'code…', status: 'done' },
      },
    })
    const detail = selectSpriteDetail(roster, 'a')
    expect(detail).not.toBeNull()
    expect(detail!.id).toBe('a')
    expect(detail!.name).toBe('规划')
    expect(detail!.text).toBe('先拆步骤')
    expect(detail!.hasStream).toBe(true)
    expect(selectSpriteDetail(roster, 'missing')).toBeNull()
    expect(selectSpriteDetail(roster, null)).toBeNull()
  })
})

describe('skin / island prefs', () => {
  beforeEach(() => {
    try {
      localStorage.removeItem(SKIN_STORAGE_KEY)
      localStorage.removeItem(ISLAND_ENABLED_KEY)
    } catch {
      /* jsdom always has localStorage */
    }
  })

  it('persists skin A then B', () => {
    saveStudioSkin('study')
    expect(loadStudioSkin()).toBe('study')
    saveStudioSkin('cabin')
    expect(loadStudioSkin()).toBe('cabin')
    saveStudioSkin('studio')
    expect(loadStudioSkin()).toBe('studio')
  })

  it('persists island enabled toggle', () => {
    expect(loadIslandEnabled()).toBe(true)
    saveIslandEnabled(false)
    expect(loadIslandEnabled()).toBe(false)
    saveIslandEnabled(true)
    expect(loadIslandEnabled()).toBe(true)
  })
})
