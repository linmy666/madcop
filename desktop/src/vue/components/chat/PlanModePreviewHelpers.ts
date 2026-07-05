/** PlanModePreview helpers — extracted from PlanModePreview.vue for re-export */
import type { AllowedPrompt, PlanPreviewModel } from './PlanModePreview.vue'

export const EXIT_PLAN_MODE_TOOL_NAME = 'ExitPlanMode'

export function isExitPlanModeTool(toolName: string): boolean {
  return toolName === EXIT_PLAN_MODE_TOOL_NAME
}

function asRecord(input: unknown): Record<string, unknown> {
  if (input && typeof input === 'object' && !Array.isArray(input)) {
    return input as Record<string, unknown>
  }
  return {}
}

function extractTextContent(content: unknown): string | null {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content
      .map((chunk: any) => (typeof chunk === 'string' ? chunk : chunk?.text || ''))
      .filter(Boolean)
      .join('\n')
  }
  if (content && typeof content === 'object') {
    return JSON.stringify(content, null, 2)
  }
  return null
}

function getString(record: Record<string, unknown>, key: string): string | null {
  const val = record[key]
  return typeof val === 'string' && val ? val : null
}

function extractApprovedPlan(_text: string): string {
  return ''
}

function extractPlanFilePath(_text: string): string {
  return ''
}

function extractAllowedPrompts(prompts: unknown): AllowedPrompt[] {
  if (Array.isArray(prompts)) {
    return prompts
      .filter((p): p is { tool: string; prompt: string } =>
        p && typeof p === 'object' && typeof p.tool === 'string' && typeof p.prompt === 'string'
      )
      .map((p) => ({ tool: p.tool, prompt: p.prompt }))
  }
  return []
}

export function extractPlanPreview(input: unknown, resultContent?: unknown): PlanPreviewModel {
  const inputRecord = asRecord(input)
  const resultText = extractTextContent(resultContent)
  const approvedPlan = resultText ? extractApprovedPlan(resultText) : ''

  return {
    plan:
      getString(inputRecord, 'plan') ||
      getString(inputRecord, 'planContent') ||
      approvedPlan,
    filePath:
      getString(inputRecord, 'planFilePath') ||
      getString(inputRecord, 'filePath') ||
      (resultText ? extractPlanFilePath(resultText) : ''),
    allowedPrompts: extractAllowedPrompts(inputRecord.allowedPrompts),
  }
}
