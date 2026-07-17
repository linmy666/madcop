import { describe, expect, it } from 'vitest'
import {
  sanitizeAgentDisplayText,
  stripMarkdownLite,
  mapEngineErrorLabel,
} from './agentDisplayText'

describe('stripMarkdownLite', () => {
  it('removes bold markers', () => {
    expect(stripMarkdownLite('## 审查结果：上游 **完成**')).toBe('审查结果：上游 完成')
  })
})

describe('mapEngineErrorLabel', () => {
  it('maps 404 model not found', () => {
    const raw =
      "[ReAct engine error: Error code: 404 - {'error': {'message': 'model is not found', 'type': 'not_found_error'}}]"
    expect(mapEngineErrorLabel(raw)).toBe('模型不可用')
  })
})

describe('sanitizeAgentDisplayText', () => {
  it('cleans markdown for bubbles', () => {
    expect(sanitizeAgentDisplayText('**审查结果**：上游 ok', 40)).toBe('审查结果：上游 ok')
  })

  it('shortens engine errors', () => {
    const raw =
      "[ReAct engine error: Error code: 404 - {'error': {'message': 'model is not found'}}]"
    expect(sanitizeAgentDisplayText(raw)).toBe('模型不可用')
  })

  it('truncates long plain text', () => {
    const long = '甲'.repeat(80)
    const out = sanitizeAgentDisplayText(long, 20)
    expect(out.length).toBeLessThanOrEqual(20)
    expect(out.endsWith('…')).toBe(true)
  })
})
