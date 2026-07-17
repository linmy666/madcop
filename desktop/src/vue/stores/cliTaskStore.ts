import { defineStore } from 'pinia'
import { cliTasksApi } from '../api/cliTasks'
import type { CLITask } from '../../types/cliTask'

/**
 * Per-session CLI / TodoWrite tasks — wired to /api/tasks.
 */

export type { CLITask }

export type TodoItem = {
  content: string
  status: string
  activeForm?: string
}

function normalizeTask(raw: any, fallbackListId: string): CLITask {
  return {
    id: String(raw?.id ?? raw?.taskId ?? ''),
    subject: raw?.subject || raw?.content || raw?.name || '',
    description: raw?.description || '',
    status: (['pending', 'in_progress', 'completed'].includes(raw?.status)
      ? raw.status
      : 'pending') as CLITask['status'],
    taskListId: String(raw?.taskListId || raw?.listId || fallbackListId),
    activeForm: raw?.activeForm,
    owner: raw?.owner,
    blocks: Array.isArray(raw?.blocks) ? raw.blocks : [],
    blockedBy: Array.isArray(raw?.blockedBy) ? raw.blockedBy : [],
  }
}

export const useCLITaskStore = defineStore('cliTask', {
  state: () => ({
    sessionId: null as string | null,
    tasks: [] as CLITask[],
    resetting: false,
    expanded: false,
    completedAndDismissed: false,
    dismissedCompletionKey: null as string | null,
    error: null as string | null,
  }),

  actions: {
    async fetchSessionTasks(sessionId: string) {
      this.sessionId = sessionId
      this.resetting = false
      this.completedAndDismissed = false
      this.dismissedCompletionKey = null
      this.error = null
      try {
        // Prefer per-list (session id as list id), fall back to all tasks
        let list: any[] = []
        try {
          const data = await cliTasksApi.getTasksForList(sessionId)
          list = Array.isArray((data as any)?.tasks) ? (data as any).tasks : []
        } catch {
          const data = await cliTasksApi.listAll()
          const all = Array.isArray((data as any)?.tasks) ? (data as any).tasks : []
          list = all.filter(
            (t: any) =>
              t?.taskListId === sessionId ||
              t?.listId === sessionId ||
              t?.sessionId === sessionId,
          )
        }
        this.tasks = list.map((t) => normalizeTask(t, sessionId))
      } catch (err) {
        this.error = (err as Error).message
        this.tasks = []
      }
    },

    async refreshTasks(targetSessionId?: string) {
      const sessionId = targetSessionId ?? this.sessionId
      if (!sessionId) return
      await this.fetchSessionTasks(sessionId)
    },

    setTasksFromTodos(todos: TodoItem[], targetSessionId?: string) {
      const sessionId = targetSessionId ?? this.sessionId
      if (!sessionId) return
      this.tasks = todos.map((todo, i) => ({
        id: String(i + 1),
        subject: todo.content,
        description: '',
        activeForm: todo.activeForm,
        status: (['pending', 'in_progress', 'completed'].includes(todo.status)
          ? todo.status
          : 'pending') as CLITask['status'],
        blocks: [],
        blockedBy: [],
        taskListId: sessionId,
      }))
    },

    markCompletedAndDismissed(_targetSessionId?: string) {
      this.completedAndDismissed = true
      this.expanded = false
    },

    async resetCompletedTasks(targetSessionId?: string) {
      const sessionId = targetSessionId ?? this.sessionId
      this.resetting = true
      try {
        if (sessionId) {
          await cliTasksApi.resetTaskList(sessionId)
        }
      } catch (err) {
        this.error = (err as Error).message
      }
      this.tasks = []
      this.completedAndDismissed = true
      this.expanded = false
      this.resetting = false
    },

    clearTasks(_targetSessionId?: string) {
      this.sessionId = null
      this.tasks = []
      this.resetting = false
      this.completedAndDismissed = false
      this.dismissedCompletionKey = null
      this.error = null
    },
  },
})
