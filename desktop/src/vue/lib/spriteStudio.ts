/**
 * MadCop Sprite Studio — pure roster / pose / selection / skin helpers.
 * No Vue. Driven by real session agentStreams + deepRoute + clarify signals.
 */

export type SpritePose =
  | 'idle'
  | 'thinking'
  | 'working'
  | 'tool_file'
  | 'tool_web'
  | 'blocked'
  | 'done'
  | 'error'

export type StudioSkinId = 'studio' | 'study' | 'cabin'

export interface AgentStreamInput {
  name: string
  color: string
  text: string
  status: 'running' | 'done' | 'error'
  elapsed_ms?: number
}

export interface DeepRouteInput {
  category?: string
  specialists?: string[]
  label_zh?: string
  label_en?: string
  reason?: string
  pipeline?: string[]
  matched?: string[]
}

export interface SpriteRosterInput {
  agentStreams?: Record<string, AgentStreamInput> | null
  deepRoute?: DeepRouteInput | null
  clarificationPending?: { question?: string; options?: string[] } | null
  activeToolName?: string | null
  /** chatStore ChatState plus stream labels: idle|busy|streaming|tool_executing|… */
  chatState?: string | null
}

export interface SpriteAgent {
  id: string
  name: string
  color: string
  pose: SpritePose
  role: string
  station: string
  text: string
  status: 'running' | 'done' | 'error' | 'idle' | 'pending'
  bubble: string
  elapsed_ms?: number
}

export interface SpriteDetail {
  id: string
  name: string
  color: string
  pose: SpritePose
  text: string
  status: SpriteAgent['status']
  bubble: string
  elapsed_ms?: number
  /** True when detail came from a live agentStreams entry */
  hasStream: boolean
}

/** Role → display defaults (stations in the studio scene). */
export const ROLE_META: Record<
  string,
  { label: string; color: string; station: string }
> = {
  planner: { label: '规划', color: '#7C3AED', station: 'planner' },
  coder: { label: '写码', color: '#2563EB', station: 'coder' },
  designer: { label: '设计', color: '#EC4899', station: 'designer' },
  researcher: { label: '调研', color: '#0891B2', station: 'researcher' },
  reviewer: { label: '审核', color: '#F59E0B', station: 'reviewer' },
  synthesizer: { label: '合成', color: '#10B981', station: 'synthesizer' },
  general: { label: '助手', color: '#7C3AED', station: 'general' },
}

export const STUDIO_STATIONS = [
  'planner',
  'coder',
  'designer',
  'researcher',
  'reviewer',
  'synthesizer',
  'general',
] as const

export const STUDIO_SKINS: {
  id: StudioSkinId
  label: string
  labelEn: string
  hint: string
}[] = [
  { id: 'studio', label: '默认工作室', labelEn: 'Studio', hint: '明亮工位' },
  { id: 'study', label: '书房', labelEn: 'Study', hint: '暖纸木色' },
  { id: 'cabin', label: '船舱', labelEn: 'Cabin', hint: '星露谷风' },
]

export const SKIN_STORAGE_KEY = 'madcop_sprite_studio_skin'
export const ISLAND_ENABLED_KEY = 'madcop_sprite_island_enabled'
export const ISLAND_COLLAPSED_KEY = 'madcop_sprite_island_collapsed'
export const AGENT_HUB_VIEW_KEY = 'madcop_agent_hub_view'

export function inferRole(id: string, name?: string): string {
  const s = `${id} ${name || ''}`.toLowerCase()
  if (/(plan|规划|planner)/.test(s)) return 'planner'
  if (/(code|coder|写码|编程|dev)/.test(s)) return 'coder'
  if (/(design|设计|ui|ux)/.test(s)) return 'designer'
  if (/(research|调研|search|检索)/.test(s)) return 'researcher'
  if (/(review|审核|审查)/.test(s)) return 'reviewer'
  if (/(synth|合成|汇总|writer|writing)/.test(s)) return 'synthesizer'
  return 'general'
}

export function poseFromToolName(toolName: string | null | undefined): SpritePose | null {
  if (!toolName) return null
  const t = toolName.toLowerCase()
  if (/(write|read|edit|file|xlsx|path|dir|workspace)/.test(t)) return 'tool_file'
  if (/(web|search|fetch|http|browse|url)/.test(t)) return 'tool_web'
  return 'working'
}

/** True when the session is mid-turn (matches chatStore ChatState + stream labels). */
export function isChatBusy(chatState: string | null | undefined): boolean {
  if (!chatState) return false
  return (
    chatState === 'busy' ||
    chatState === 'streaming' ||
    chatState === 'sending' ||
    chatState === 'thinking' ||
    chatState === 'tool_executing'
  )
}

function bubbleForPose(pose: SpritePose, text: string, clarifyQ?: string): string {
  if (pose === 'blocked' && clarifyQ) return clarifyQ.slice(0, 48)
  if (pose === 'error') return '出错了'
  if (pose === 'done') return '完成'
  if (pose === 'tool_file') return '读写文件…'
  if (pose === 'tool_web') return '检索中…'
  if (pose === 'thinking') return '思考中…'
  if (pose === 'working') {
    const t = (text || '').replace(/\s+/g, ' ').trim()
    return t ? t.slice(0, 36) + (t.length > 36 ? '…' : '') : '工作中…'
  }
  return ''
}

function poseFromStreamStatus(
  status: AgentStreamInput['status'],
  opts: {
    clarificationPending: boolean
    activeToolName?: string | null
    text: string
  },
): SpritePose {
  if (status === 'error') return 'error'
  if (status === 'done') return 'done'
  // running
  if (opts.clarificationPending) return 'blocked'
  const toolPose = poseFromToolName(opts.activeToolName)
  if (toolPose) return toolPose
  if (opts.text && opts.text.length > 0) return 'working'
  return 'thinking'
}

/**
 * Build the sprite roster from real session signals.
 * Prefer live agentStreams; fall back to deepRoute specialists; empty when idle.
 */
export function buildSpriteRoster(input: SpriteRosterInput): SpriteAgent[] {
  const streams = input.agentStreams || {}
  const streamIds = Object.keys(streams)
  const clarify = !!input.clarificationPending
  const clarifyQ = input.clarificationPending?.question
  // chatStore sets 'busy' on sendMessage; 'streaming' only after assistant
  // text tokens. Also accept legacy / thinking-adjacent labels.
  const busy = isChatBusy(input.chatState)

  if (streamIds.length > 0) {
    return streamIds.map((id) => {
      const s = streams[id]
      const role = inferRole(id, s.name)
      const meta = ROLE_META[role] || ROLE_META.general
      const pose = poseFromStreamStatus(s.status, {
        clarificationPending: clarify && s.status === 'running',
        activeToolName: s.status === 'running' ? input.activeToolName : null,
        text: s.text || '',
      })
      return {
        id,
        name: s.name || meta.label,
        color: s.color || meta.color,
        pose,
        role,
        station: meta.station,
        text: s.text || '',
        status: s.status,
        bubble: bubbleForPose(pose, s.text || '', clarifyQ),
        elapsed_ms: s.elapsed_ms,
      }
    })
  }

  const specialists = input.deepRoute?.specialists || []
  if (specialists.length > 0) {
    return specialists.map((raw, i) => {
      const id = String(raw)
      const role = inferRole(id, id)
      const meta = ROLE_META[role] || ROLE_META.general
      let pose: SpritePose = 'idle'
      let status: SpriteAgent['status'] = 'idle'
      if (busy) {
        pose = clarify ? 'blocked' : i === 0 ? 'thinking' : 'idle'
        status = 'pending'
      }
      if (clarify) pose = 'blocked'
      return {
        id,
        name: meta.label !== '助手' ? meta.label : id,
        color: meta.color,
        pose,
        role,
        station: meta.station,
        text: '',
        status,
        bubble: bubbleForPose(pose, '', clarifyQ),
      }
    })
  }

  // Calm solo sprite while the main agent is busy without multi-agent streams
  if (busy) {
    const toolPose = poseFromToolName(input.activeToolName)
    const pose: SpritePose = clarify
      ? 'blocked'
      : toolPose || 'thinking'
    return [
      {
        id: 'main',
        name: 'MadCop',
        color: ROLE_META.general.color,
        pose,
        role: 'general',
        station: 'general',
        text: '',
        status: 'running',
        bubble: bubbleForPose(pose, '', clarifyQ),
      },
    ]
  }

  return []
}

/** Whether the island should render a calm idle dock (no multi-agent). */
export function shouldShowCalmIsland(input: SpriteRosterInput): boolean {
  const roster = buildSpriteRoster(input)
  if (roster.length > 0) return true
  // Fully idle: optional calm single — hide by default (empty roster)
  return false
}

/**
 * Resolve selection to that agent’s detail from the same roster + streams.
 * Does not reimplement stream storage — reads text/status from the sprite.
 */
export function selectSpriteDetail(
  roster: SpriteAgent[],
  selectedId: string | null | undefined,
): SpriteDetail | null {
  if (!selectedId) return null
  const sprite = roster.find((s) => s.id === selectedId)
  if (!sprite) return null
  return {
    id: sprite.id,
    name: sprite.name,
    color: sprite.color,
    pose: sprite.pose,
    text: sprite.text,
    status: sprite.status,
    bubble: sprite.bubble,
    elapsed_ms: sprite.elapsed_ms,
    hasStream: !!(sprite.text && sprite.text.length > 0) || sprite.status === 'running' || sprite.status === 'done' || sprite.status === 'error',
  }
}

export function poseLabel(pose: SpritePose): string {
  const map: Record<SpritePose, string> = {
    idle: '空闲',
    thinking: '思考',
    working: '工作中',
    tool_file: '文件',
    tool_web: '联网',
    blocked: '等待你',
    done: '完成',
    error: '失败',
  }
  return map[pose] || pose
}

// ── Preferences (localStorage; SSR-safe) ──────────────────────────────

function lsGet(key: string): string | null {
  try {
    if (typeof localStorage === 'undefined') return null
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function lsSet(key: string, value: string): void {
  try {
    if (typeof localStorage === 'undefined') return
    localStorage.setItem(key, value)
  } catch {
    /* ignore */
  }
}

export function loadStudioSkin(): StudioSkinId {
  const v = lsGet(SKIN_STORAGE_KEY)
  if (v === 'study' || v === 'cabin' || v === 'studio') return v
  return 'studio'
}

export function saveStudioSkin(skin: StudioSkinId): void {
  lsSet(SKIN_STORAGE_KEY, skin)
}

export function loadIslandEnabled(): boolean {
  const v = lsGet(ISLAND_ENABLED_KEY)
  if (v === null) return true
  return v !== '0' && v !== 'false'
}

export function saveIslandEnabled(on: boolean): void {
  lsSet(ISLAND_ENABLED_KEY, on ? '1' : '0')
}

export function loadIslandCollapsed(): boolean {
  return lsGet(ISLAND_COLLAPSED_KEY) === '1'
}

export function saveIslandCollapsed(collapsed: boolean): void {
  lsSet(ISLAND_COLLAPSED_KEY, collapsed ? '1' : '0')
}

export function loadAgentHubView(): 'topology' | 'studio' {
  return lsGet(AGENT_HUB_VIEW_KEY) === 'studio' ? 'studio' : 'topology'
}

export function saveAgentHubView(view: 'topology' | 'studio'): void {
  lsSet(AGENT_HUB_VIEW_KEY, view)
}
