import { defineStore } from 'pinia'

/**
 * Pinia mirror of stores/workspaceChatContextStore.ts
 * Workspace chat references (file selections, code snippets, etc.).
 */

export type WorkspaceChatReference = {
  id: string
  kind: string
  path: string
  name: string
  isDirectory?: boolean
  lineStart?: number
  lineEnd?: number
  note?: string
  quote?: string
  messageId?: string
}

function makeReferenceId(reference: Omit<WorkspaceChatReference, 'id'>): string {
  const linePart = reference.lineStart
    ? `${reference.lineStart}-${reference.lineEnd ?? reference.lineStart}`
    : reference.messageId ?? 'file'
  const notePart = (reference.note?.trim() || reference.quote?.trim() || '').slice(0, 48)
  return `${reference.kind}:${reference.path}:${linePart}:${notePart}`
}

export function formatWorkspaceReferencePrompt(_references: WorkspaceChatReference[]): string {
  return ''
}

export const useWorkspaceChatContextStore = defineStore('workspaceChatContext', {
  state: () => ({
    referencesBySession: {} as Record<string, WorkspaceChatReference[]>,
  }),

  actions: {
    addReference(sessionId: string, input: Omit<WorkspaceChatReference, 'id'> & { id?: string }) {
      const existing = this.referencesBySession[sessionId] || []
      const reference: WorkspaceChatReference = {
        ...input,
        id: input.id ?? makeReferenceId(input as Omit<WorkspaceChatReference, 'id'>),
      }
      this.referencesBySession[sessionId] = [...existing, reference]
    },
    removeReference(sessionId: string, referenceId: string) {
      const refs = this.referencesBySession[sessionId]
      if (refs) {
        this.referencesBySession[sessionId] = refs.filter(r => r.id !== referenceId)
      }
    },
    clearReferences(sessionId: string) {
      delete this.referencesBySession[sessionId]
    },
    clearSession(sessionId: string) {
      delete this.referencesBySession[sessionId]
    },
  },
})
