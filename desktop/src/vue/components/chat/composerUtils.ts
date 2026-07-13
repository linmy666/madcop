// Real implementation of slash-command helpers for the Vue composer.
// (Originally a stub created during the React→Vue migration; the stub made
// the slash menu never open because findSlashTrigger/findSlashToken always
// returned null. Now functional.)

export interface SlashCommandOption {
  name: string
  description?: string
  argumentHint?: string
}

export type SlashCommand = SlashCommandOption

export type SlashUiAction =
  | { type: 'panel'; command: string }
  | { type: 'settings'; tab: string }
  | null

interface SlashToken {
  filter: string
}

interface SlashReplacement {
  value: string
  cursorPos: number
}

// Resolve the bounds of the slash token the cursor is currently inside, or
// null if the cursor is not inside a slash command being typed. A slash only
// counts as a trigger when it begins a token (start of input or after
// whitespace) and the partial command name contains no space yet.
function slashTokenBounds(value: string, cursorPos: number): { start: number; end: number } | null {
  const before = value.slice(0, cursorPos)
  const slashIdx = before.lastIndexOf('/')
  if (slashIdx === -1) return null
  if (slashIdx > 0 && !/\s/.test(before[slashIdx - 1])) return null
  const tokenText = before.slice(slashIdx + 1)
  if (/\s/.test(tokenText)) return null
  let endIdx = slashIdx + 1
  while (endIdx < value.length && !/\s/.test(value[endIdx])) endIdx++
  return { start: slashIdx, end: endIdx }
}

export function findSlashTrigger(value: string, cursorPos: number): SlashToken | null {
  const bounds = slashTokenBounds(value, cursorPos)
  if (!bounds) return null
  return { filter: value.slice(bounds.start + 1, cursorPos) }
}

export function findSlashToken(text: string, cursorPos: number): SlashToken | null {
  return findSlashTrigger(text, cursorPos)
}

export function replaceSlashToken(
  value: string,
  cursorPos: number,
  command: string,
  opts?: { trailingSpace?: boolean },
): SlashReplacement | null {
  const bounds = slashTokenBounds(value, cursorPos)
  if (!bounds) return null
  const trailing = opts?.trailingSpace === false ? '' : ' '
  const insertText = command ? `/${command}${trailing}` : '/'
  const newValue = value.slice(0, bounds.start) + insertText + value.slice(bounds.end)
  return { value: newValue, cursorPos: bounds.start + insertText.length }
}

export function replaceSlashCommand(
  value: string,
  cursorPos: number,
  command: string,
): SlashReplacement | null {
  return replaceSlashToken(value, cursorPos, command)
}

export function insertSlashTrigger(value: string, cursorPos: number): SlashReplacement {
  const before = value.slice(0, cursorPos)
  const after = value.slice(cursorPos)
  const newValue = `${before}/${after}`
  return { value: newValue, cursorPos: cursorPos + 1 }
}

export function filterSlashCommands(commands: SlashCommandOption[], filter: string): SlashCommandOption[] {
  const f = (filter || '').trim().toLowerCase()
  if (!f) return commands
  return commands.filter(
    (c) =>
      (c.name && c.name.toLowerCase().includes(f)) ||
      (c.description && c.description.toLowerCase().includes(f)),
  )
}

const PANEL_COMMANDS: Record<string, string> = {
  mcp: 'mcp',
  skills: 'skills',
  help: 'help',
  status: 'status',
  cost: 'cost',
  context: 'context',
}

export function resolveSlashUiAction(command: string): SlashUiAction {
  const name = (command || '').trim().toLowerCase()
  if (name in PANEL_COMMANDS) return { type: 'panel', command: PANEL_COMMANDS[name] }
  if (name === 'settings') return { type: 'settings', tab: 'general' }
  return null
}

export function buildAgentSlashCommands(_agents: any[]): SlashCommandOption[] {
  // Agent-derived slash commands are not wired in the Vue build yet.
  return []
}

export function appendAgentSlashCommands(
  commands: SlashCommandOption[],
  agentCommands: SlashCommandOption[],
): SlashCommandOption[] {
  return [...commands, ...agentCommands]
}

export function mergeSlashCommands(a: SlashCommandOption[], b: SlashCommandOption[]): SlashCommandOption[] {
  return [...a, ...b]
}

export function getLocalizedFallbackCommands(_t: any): SlashCommandOption[] {
  return [
    { name: 'clear', description: '清空当前会话的对话历史' },
    { name: 'help', description: '查看可用命令与本地面板' },
    { name: 'mcp', description: '查看 MCP 连接器状态' },
    { name: 'skills', description: '查看已安装的技能' },
    { name: 'status', description: '查看会话与运行环境状态' },
    { name: 'cost', description: '查看本次会话的 token 消耗' },
    { name: 'context', description: '查看上下文窗口占用情况' },
    { name: 'model', description: '查看或切换当前模型' },
  ]
}

export function extractPlanPreview(_content: string): any {
  return null
}

export function isExitPlanModeTool(_toolName: string): boolean {
  return false
}
