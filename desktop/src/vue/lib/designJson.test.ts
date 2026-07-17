import { describe, expect, it } from 'vitest'
import {
  autoRepairDesignData,
  emptyDesignData,
  extractDesignJson,
  parseAndRepairDesignResponse,
} from './designJson'
import { designDataToHtml } from './designRender'

describe('extractDesignJson', () => {
  it('parses raw design JSON', () => {
    const raw = JSON.stringify({
      root: { props: { bgColor: '#fff' } },
      content: [{ type: 'Header', props: { text: 'Hi' } }],
    })
    const p = extractDesignJson(raw)
    expect(p).toBeTruthy()
    expect(p.content).toHaveLength(1)
    expect(p.content[0].type).toBe('Header')
  })

  it('strips markdown fence and leading prose', () => {
    const text = `这是设计稿：
\`\`\`json
{"root":{"props":{}},"content":[{"type":"Button","props":{"text":"Go"}}]}
\`\`\`
希望对你有帮助`
    const p = extractDesignJson(text)
    expect(p?.content?.[0]?.type).toBe('Button')
  })

  it('returns null when no content array', () => {
    expect(extractDesignJson('{"foo":1}')).toBeNull()
    expect(extractDesignJson('')).toBeNull()
  })
})

describe('autoRepairDesignData', () => {
  it('fills root defaults and missing props', () => {
    const repaired = autoRepairDesignData({
      content: [{ type: 'Header', props: {} }],
    })
    expect(repaired.root.props.bgColor).toBe('#FFFFFF')
    expect(repaired.root.props.padding).toBe(40)
    expect(repaired.content[0].props.text).toBe('标题')
    expect(repaired.content[0].props.level).toBe('2')
  })

  it('maps unknown component types to visible Paragraph fallback', () => {
    const repaired = autoRepairDesignData({
      root: { props: {} },
      content: [{ type: 'MagicWidget', props: { foo: 1 } }],
    })
    expect(repaired.content).toHaveLength(1)
    expect(repaired.content[0].type).toBe('Paragraph')
    expect(repaired.content[0].props.text).toContain('未知组件')
    expect(repaired.content[0].props.text).toContain('MagicWidget')
  })

  it('repairs nested children', () => {
    const repaired = autoRepairDesignData({
      content: [
        {
          type: 'Card',
          props: {},
          children: [{ type: 'Paragraph', props: {} }],
        },
      ],
    })
    expect(repaired.content[0].type).toBe('Card')
    expect(repaired.content[0].children?.[0].props.text).toBe('文字')
  })

  it('emptyDesignData is canvas-openable', () => {
    const e = emptyDesignData()
    expect(Array.isArray(e.content)).toBe(true)
    expect(e.root.props.bgColor).toBeTruthy()
  })
})

describe('parseAndRepairDesignResponse', () => {
  it('end-to-end fences + missing defaults', () => {
    const llm = '```json\n{"content":[{"type":"Input","props":{"placeholder":"邮箱"}}]}\n```'
    const data = parseAndRepairDesignResponse(llm)
    expect(data).toBeTruthy()
    expect(data!.content[0].type).toBe('Input')
    expect(data!.content[0].props.width).toBe(300)
    expect(data!.root.props.padding).toBe(40)
  })
})

describe('designDataToHtml', () => {
  it('embeds content text and is a full HTML document', () => {
    const html = designDataToHtml({
      root: { props: { bgColor: '#FAFAFA', padding: 24 } },
      content: [
        { type: 'Header', props: { text: '登录', level: '1', fontSize: 28 } },
        { type: 'Button', props: { text: '提交', variant: 'primary' } },
      ],
    })
    expect(html.startsWith('<!DOCTYPE html>')).toBe(true)
    expect(html).toContain('登录')
    expect(html).toContain('提交')
    expect(html).toContain('#FAFAFA')
    expect(html).not.toContain('/preview/')
  })

  it('empty canvas shows placeholder', () => {
    const html = designDataToHtml(emptyDesignData())
    expect(html).toContain('空画布')
  })
})
