import { defineStore } from 'pinia'

/**
 * Pinia mirror of stores/cliTaskStore.ts
 * Per-session CLI tasks (TodoWrite integration).
 */

export type CLITask = {
  id: string
  subject: string
  description: string
  status: 'pending' | 'in_progress' | 'completed'
  taskListId: string
  activeForm?: string
  owner?: string
  blocks: string[]
  blockedBy: string[]
}

export type TodoItem = {
  content: string
  status: string
  activeForm?: string
}

export const useCLITaskStore = defineStore('cliTask', {
  state: () => ({
    sessionId: null as string | null,
    tasks: [] as CLITask[],
    resetting: false,
    expanded: false,
    completedAndDismissed: false,
    dismissedCompletionKey: null as string | null,
  }),

  actions: {
    async fetchSessionTasks(sessionId: string) {
      this.sessionId = sessionId
      this.tasks = []
      this.resetting = false
      this.completedAndDismissed = false
      this.dismissedCompletionKey = null
      // Would fetch from CLI task API
    },
    async refreshTasks(targetSessionId?: string) {
      const sessionId = targetSessionId ?? this.sessionId
      if (!sessionId) return
      // Would fetch from API
    },
    setTasksFromTodos(todos: TodoItem[], targetSessionId?: string) {
      const sessionId = targetSessionId ?? this.sessionId
      if (!sessionId) return
      this.tasks = todos.map((todo, i) => ({
        id: String(i + 1),
        subject: todo.content,
        description: '',
        activeForm: todo.activeForm,
        status: (['pending', 'in_progress', 'completed'].includes(todo.status) ? todo.status : 'pending') as CLITask['status'],
        blocks: [],
        blockedBy: [],
        taskListId: sessionId,
      }))
    },
    markCompletedAndDismissed(_targetSessionId?: string) {
      this.completedAndDismissed = true
      this.expanded = false
    },
    async resetCompletedTasks(_targetSessionId?: string) {
      this.tasks = []
      this.resetting = true
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
      this.expanded = false
    },
    toggleExpanded() {
      this.expanded = !this.expanded
    },
  },
})
