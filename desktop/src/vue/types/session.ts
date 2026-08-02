// Source: src/server/services/sessionService.ts

export type SessionListItem = {
  id: string
  title: string
  createdAt: string
  modifiedAt: string
  messageCount: number
  /** Project root path (always set, non-null). Use this unless you need
   *  a sub-folder / git worktree — in that case use `workDir`. */
  projectPath: string
  workDir: string | null
  workDirExists: boolean
  permissionMode?: string
}

export type MessageUsage = {
  input_tokens?: number
  output_tokens?: number
  cache_read_input_tokens?: number
  cache_creation_input_tokens?: number
}

export type MessageEntry = {
  id: string
  type: 'user' | 'assistant' | 'system' | 'tool_use' | 'tool_result'
  content: unknown
  toolUseResult?: unknown
  timestamp: string
  model?: string
  usage?: MessageUsage
  parentUuid?: string
  parentToolUseId?: string
  isSidechain?: boolean
}

export type SessionDetail = SessionListItem & {
  messages: MessageEntry[]
}
