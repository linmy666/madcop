/**
 * composerUtils — Vue port of components/chat/composerUtils.tsx
 * Utility functions for slash command parsing, filtering, and merging.
 */

// ─── Types ───────────────────────────────────────────────────────

export type SlashCommand = {
  name: string
  description: string
  argumentHint?: string
  category?: string
  icon?: string
  source?: string
}

export type AgentSlashCommand = SlashCommand & {
  agentId: string
  agentName: string
  description: string
  argumentHint?: string
}

export type AgentInfo = {
  id: string
  name: string
  status: string
}

export type LocalSlashCommandName =
  | 'mcp' | 'skills' | 'help' | 'status' | 'cost' | 'context'
  | 'terminal' | 'browser' | 'workflows' | 'traces' | 'design'
  | 'schedule' | 'doctor' | 'workspace'

export type SlashUiAction =
  | { type: 'panel'; command: LocalSlashCommandName }
  | { type: 'settings'; tab: string }
  | null

// ─── findSlashTrigger ────────────────────────────────────────────

function findSlashTrigger(value: string, cursorPos: number): { filter: string; start: number; end: number } | null {
  let start = -1
  let pos = cursorPos - 1
  while (pos >= 0) {
    const ch = value[pos]
    if (ch === '/') {
      if (pos === 0 || /\s/.test(value[pos - 1] ?? '')) {
        start = pos
        break
      }
      break
    }
    if (/\s/.test(ch)) {
      break
    }
    pos--
  }

  if (start < 0) return null

  const filter = value.slice(start + 1, cursorPos)
  if (/\s/.test(filter)) return null

  return { filter, start, end: cursorPos }
}

// ─── replaceSlashToken ───────────────────────────────────────────

function replaceSlashToken(
  input: string,
  cursorPos: number,
  command: string,
  options?: { trailingSpace?: boolean },
): { value: string; cursorPos: number } {
  const opts = options || { trailingSpace: true }
  const token = findSlashTrigger(input, cursorPos)

  if (!token) {
    // No slash token found — just insert '/' at cursor
    const before = input.slice(0, cursorPos)
    const after = input.slice(cursorPos)
    const leadingSpace = before.length > 0 && !/\s$/.test(before) ? ' ' : ''
    const trailingSpace = opts.trailingSpace ? ' ' : ''
    const newValue = before + leadingSpace + '/' + trailingSpace + after
    return {
      value: newValue,
      cursorPos: cursorPos + leadingSpace.length + 1 + trailingSpace.length,
    }
  }

  // Remove the slash token and insert the command
  const before = input.slice(0, token.start)
  const after = input.slice(token.end)
  const leadingSpace = before.length > 0 && !/\s$/.test(before) ? ' ' : ''
  const trailingSpace = opts.trailingSpace ? ' ' : ''
  const commandText = command.startsWith('/') ? command : '/' + command

  const newValue = before + leadingSpace + commandText + trailingSpace + after
  return {
    value: newValue,
    cursorPos: before.length + leadingSpace.length + commandText.length + trailingSpace.length,
  }
}

// ─── filterSlashCommands ─────────────────────────────────────────

function filterSlashCommands(
  commands: SlashCommand[],
  filter: string,
): SlashCommand[] {
  if (!filter) return commands

  const q = filter.toLowerCase().trim()
  return commands.filter((cmd) => {
    const nameMatch = cmd.name.toLowerCase().startsWith(q)
    const descMatch = cmd.description.toLowerCase().includes(q)
    return nameMatch || descMatch
  })
}

// ─── buildAgentSlashCommands ─────────────────────────────────────

function buildAgentSlashCommands(activeAgents: AgentInfo[]): AgentSlashCommand[] {
  return activeAgents
    .filter((agent) => agent.status === 'active')
    .map((agent) => ({
      name: agent.name.toLowerCase().replace(/\s+/g, '-'),
      agentId: agent.id,
      agentName: agent.name,
      description: `Run "${agent.name}" agent`,
      category: 'agent',
      source: 'agent',
    }))
}

// ─── appendAgentSlashCommands ────────────────────────────────────

function appendAgentSlashCommands(
  slashCommands: SlashCommand[],
  agentSlashCommands: AgentSlashCommand[],
): SlashCommand[] {
  if (agentSlashCommands.length === 0) return slashCommands
  // Filter out any existing agent commands to avoid duplicates
  const baseCommands = slashCommands.filter((cmd) => cmd.source !== 'agent')
  return [...baseCommands, ...agentSlashCommands]
}

// ─── mergeSlashCommands ──────────────────────────────────────────

function mergeSlashCommands(
  slashCommands: SlashCommand[],
  fallbackCommands: SlashCommand[],
): SlashCommand[] {
  // Merge: use slashCommands as primary, fallback for missing commands
  const commandMap = new Map<string, SlashCommand>()

  // Add fallbacks first
  for (const cmd of fallbackCommands) {
    commandMap.set(cmd.name, cmd)
  }

  // Override with session-specific commands
  for (const cmd of slashCommands) {
    commandMap.set(cmd.name, cmd)
  }

  return Array.from(commandMap.values())
}

// ─── getLocalizedFallbackCommands ────────────────────────────────

function getLocalizedFallbackCommands(_t: any): SlashCommand[] {
  return [
    { name: '/new', description: 'Start a new chat session', category: 'session', icon: 'add_comment' },
    { name: '/stop', description: 'Stop the current generation', category: 'session', icon: 'stop_circle' },
    { name: '/settings', description: 'Open settings', category: 'app', icon: 'settings' },
    { name: '/compact', description: 'Compact the session history', category: 'session', icon: 'compress' },
    { name: '/help', description: 'Show available commands', category: 'info', icon: 'help' },
    { name: '/status', description: 'Show session status', category: 'info', icon: 'info' },
    { name: '/mcp', description: 'Manage MCP servers', category: 'tools', icon: 'dns' },
    { name: '/skills', description: 'List available skills', category: 'tools', icon: 'extension' },
    { name: '/context', description: 'Show context usage', category: 'info', icon: 'memory' },
  ]
}

// ─── resolveSlashUiAction ────────────────────────────────────────

const PANEL_COMMANDS: Set<LocalSlashCommandName> = new Set([
  'mcp', 'skills', 'help', 'status', 'cost', 'context',
  'terminal', 'browser', 'workflows', 'traces', 'design',
  'schedule', 'doctor', 'workspace',
])

const SETTINGS_TAB_MAP: Record<string, string> = {
  settings: 'general',
  models: 'models',
  appearance: 'appearance',
}

function resolveSlashUiAction(slashCmd: string): SlashUiAction {
  const name = slashCmd.toLowerCase().trim()

  if (PANEL_COMMANDS.has(name as LocalSlashCommandName)) {
    return { type: 'panel', command: name as LocalSlashCommandName }
  }

  if (SETTINGS_TAB_MAP[name]) {
    return { type: 'settings', tab: SETTINGS_TAB_MAP[name] }
  }

  return null
}

// ─── Exports ─────────────────────────────────────────────────────

export {
  findSlashTrigger,
  replaceSlashToken,
  filterSlashCommands,
  buildAgentSlashCommands,
  appendAgentSlashCommands,
  mergeSlashCommands,
  getLocalizedFallbackCommands,
  resolveSlashUiAction,
}
