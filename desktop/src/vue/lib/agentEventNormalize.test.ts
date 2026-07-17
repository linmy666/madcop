import { describe, expect, it } from 'vitest'
import {
  mapStreamStatus,
  buildTimelineFromRoster,
  countByStatus,
} from './agentEventNormalize'
import type { SpriteAgent } from './spriteStudio'

const base = (over: Partial<SpriteAgent>): SpriteAgent => ({
  id: 'a',
  name: '规划',
  color: '#7C3AED',
  pose: 'working',
  role: 'planner',
  station: 'planner',
  text: 'hello **world**',
  status: 'running',
  bubble: '工作中…',
  ...over,
})

describe('mapStreamStatus', () => {
  it('maps backend-ish statuses', () => {
    expect(mapStreamStatus('ok')).toBe('completed')
    expect(mapStreamStatus('error')).toBe('error')
    expect(mapStreamStatus('running')).toBe('running')
  })
})

describe('buildTimelineFromRoster', () => {
  it('includes tool event and sanitizes detail', () => {
    const events = buildTimelineFromRoster(
      [base({ text: '**审查** ok' })],
      'web_search',
    )
    expect(events[0].agentId).toBe('_tool')
    expect(events[0].label).toContain('web_search')
    const agent = events.find((e) => e.agentId === 'a')!
    expect(agent.detail).not.toContain('**')
  })

  it('counts statuses without tool row', () => {
    const events = buildTimelineFromRoster([
      base({ id: '1', pose: 'working', status: 'running' }),
      base({ id: '2', pose: 'slacking', status: 'done' }),
      base({ id: '3', pose: 'error', status: 'error' }),
    ])
    const c = countByStatus(events)
    expect(c.running).toBe(1)
    expect(c.error).toBe(1)
  })
})
