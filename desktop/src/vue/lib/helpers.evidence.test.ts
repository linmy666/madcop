/**
 * Durable evidence runner: drives shipped pure helpers and writes JSON snapshot.
 * Invoked as part of the acceptance vitest set.
 */
import { describe, expect, it } from 'vitest'
import { writeFileSync, mkdirSync } from 'fs'
import {
  buildSpriteRoster,
  selectSpriteDetail,
  loadStudioSkin,
  saveStudioSkin,
  isChatBusy,
} from './spriteStudio'
import { sanitizeAgentDisplayText } from './agentDisplayText'
import { buildRunAdhocPayload } from './topologyPayload'
import { isPreserveWhite, recolorImageData } from './mascotRecolor'

const SCRATCH =
  process.env.MADCOP_SCRATCH ||
  '/var/folders/lh/jp2j6wyd1q3bjqvqy58vlb500000gn/T/grok-goal-dbdce767fc6b/implementer'

describe('acceptance helper fixtures (shipped modules)', () => {
  it('roster busy/deepRoute/clarify + sanitize + select + skin + payload + eyes', () => {
    expect(isChatBusy('busy')).toBe(true)

    const busyRoster = buildSpriteRoster({
      chatState: 'busy',
      deepRoute: { specialists: ['planner', 'coder'], label_zh: '编码' },
    })
    expect(busyRoster.length).toBe(2)
    expect(busyRoster.some((r) => r.pose === 'thinking')).toBe(true)

    const clarifyRoster = buildSpriteRoster({
      agentStreams: {
        a: { name: '助手', color: '#7C3AED', text: '?', status: 'running' },
      },
      clarificationPending: { question: '选哪个？' },
    })
    expect(clarifyRoster[0].pose).toBe('blocked')

    const errLabel = sanitizeAgentDisplayText(
      "[ReAct engine error: Error code: 404 - {'error': {'message': 'model is not found'}}]",
    )
    expect(errLabel).toBe('模型不可用')
    expect(sanitizeAgentDisplayText('**审查结果**：上游 ok')).not.toContain('**')

    const two = buildSpriteRoster({
      agentStreams: {
        a: { name: '规划', color: '#7C3AED', text: '先拆步骤', status: 'running' },
        b: { name: '写码', color: '#2563EB', text: 'code', status: 'done' },
      },
    })
    const detailA = selectSpriteDetail(two, 'a')
    expect(detailA?.id).toBe('a')
    expect(detailA?.text).toBe('先拆步骤')
    expect(detailA?.hasStream).toBe(true)

    saveStudioSkin('cabin')
    expect(loadStudioSkin()).toBe('cabin')
    saveStudioSkin('studio')
    expect(loadStudioSkin()).toBe('studio')

    const payload = buildRunAdhocPayload(
      '写登录页',
      [
        {
          id: 'n1',
          label: '规划',
          agentId: 'planner',
          systemPrompt: '你是规划',
          model: 'm1',
          tools: ['read_file'],
        },
      ],
      [{ from: 'n1', to: 'n2' }],
    )
    expect(payload.nodes[0].systemPrompt).toBe('你是规划')
    expect(payload.nodes[0].agentId).toBe('planner')

    // white eyes preserved
    expect(isPreserveWhite(255, 255, 255, 255)).toBe(true)
    const px = new Uint8ClampedArray([255, 255, 255, 255, 124, 58, 237, 255])
    recolorImageData(px, '#EC4899')
    expect(px[0]).toBe(255)
    expect(px[1]).toBe(255)
    expect(px[2]).toBe(255)

    const snapshot = {
      busyRosterLen: busyRoster.length,
      clarifyPose: clarifyRoster[0].pose,
      errLabel,
      detailA: { id: detailA!.id, text: detailA!.text },
      payload: payload.nodes[0],
      skin: loadStudioSkin(),
    }
    try {
      mkdirSync(SCRATCH, { recursive: true })
      writeFileSync(`${SCRATCH}/helpers.json`, JSON.stringify(snapshot, null, 2))
      writeFileSync(
        `${SCRATCH}/helpers.log`,
        `HELPERS_OK\n${JSON.stringify(snapshot, null, 2)}\n`,
      )
    } catch (e) {
      // still pass tests if scratch unwritable
      console.warn('scratch write failed', e)
    }
  })
})
