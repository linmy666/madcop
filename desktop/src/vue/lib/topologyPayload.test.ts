import { describe, expect, it } from 'vitest'
import { buildRunAdhocPayload, applyStepStatuses } from './topologyPayload'

describe('buildRunAdhocPayload', () => {
  it('includes systemPrompt model tools for engine', () => {
    const body = buildRunAdhocPayload(
      '写登录页',
      [
        {
          id: 'n1',
          label: '规划',
          agentId: 'planner',
          model: 'gpt-test',
          systemPrompt: '你是规划',
          tools: ['read_file'],
        },
        { id: 'n2', label: '写码', agentId: 'coder' },
      ],
      [{ from: 'n1', to: 'n2' }],
    )
    expect(body.input).toBe('写登录页')
    expect(body.nodes[0].systemPrompt).toBe('你是规划')
    expect(body.nodes[0].model).toBe('gpt-test')
    expect(body.nodes[0].tools).toEqual(['read_file'])
    expect(body.nodes[0].agentId).toBe('planner')
    expect(body.edges[0]).toEqual({ from: 'n1', to: 'n2', label: '' })
  })
})

describe('applyStepStatuses', () => {
  it('maps error → failed and done → completed', () => {
    const nodes = [
      { id: 'a', status: 'running' },
      { id: 'b', status: 'running' },
    ]
    const out = applyStepStatuses(nodes, [
      { node_id: 'a', status: 'done' },
      { node_id: 'b', status: 'error' },
    ])
    expect(out.find((n) => n.id === 'a')!.status).toBe('completed')
    expect(out.find((n) => n.id === 'b')!.status).toBe('failed')
  })
})
