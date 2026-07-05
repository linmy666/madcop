// Stub — provides functions referenced by EmptySession.vue
export function findSlashToken(text: string, cursorPos: number): { filter: string } | null {
  return null
}
export function replaceSlashCommand(text: string, cursorPos: number, command: string): { value: string; cursorPos: number } | null {
  return null
}
export function insertSlashTrigger(text: string, cursorPos: number): { value: string; cursorPos: number } {
  return { value: text + '/', cursorPos: cursorPos + 1 }
}
export function filterSlashCommands(commands: any[], filter: string): any[] {
  return commands
}
export function resolveSlashUiAction(command: string): any {
  return null
}
export function buildAgentSlashCommands(agents: any[]): any[] {
  return []
}
export function appendAgentSlashCommands(commands: any[], agentCommands: any[]): any[] {
  return [...commands, ...agentCommands]
}
export function mergeSlashCommands(a: any[], b: any[]): any[] {
  return [...a, ...b]
}
export function getLocalizedFallbackCommands(t: any): any[] {
  return []
}

export function findSlashTrigger(text: string): { filter: string } | null { return null }
export function replaceSlashToken(text: string, cursor: number, token: string): { value: string; cursorPos: number } | null { return null }
export function extractPlanPreview(content: string): any { return null }
export function isExitPlanModeTool(toolName: string): boolean { return false }
