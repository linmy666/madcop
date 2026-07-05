import { defineStore } from 'pinia'

/**
 * Pinia mirror of stores/taskStore.ts
 * Scheduled/cron tasks management.
 */

export type CronTask = {
  id: string
  name: string
  prompt: string
  schedule?: string
  enabled: boolean
}

export type TaskRun = {
  id: string
  taskId: string
  status: string
  startedAt: number
}

export const useTaskStore = defineStore('task', {
  state: () => ({
    tasks: [] as CronTask[],
    recentRuns: [] as TaskRun[],
    isLoading: false,
    error: null as string | null,
  }),

  actions: {
    async fetchTasks() {
      this.isLoading = true
      this.error = null
      try {
        // Mock: would call tasksApi.list()
        this.tasks = [
          { id: '1', name: 'Daily standup', prompt: 'Generate standup notes', schedule: '0 9 * * *', enabled: true },
          { id: '2', name: 'Weekly report', prompt: 'Summarize the week', schedule: '0 9 * * 1', enabled: true },
        ]
      } catch (err) { this.error = (err as Error).message }
      this.isLoading = false
    },
    async createTask(input: any) {
      const task: CronTask = {
        id: String(Date.now()),
        name: input.name || 'New Task',
        prompt: input.prompt || '',
        schedule: input.schedule,
        enabled: true,
      }
      this.tasks.push(task)
    },
    async updateTask(id: string, updates: Partial<CronTask>) {
      const idx = this.tasks.findIndex(t => t.id === id)
      if (idx >= 0) Object.assign(this.tasks[idx], updates)
    },
    async deleteTask(id: string) {
      this.tasks = this.tasks.filter(t => t.id !== id)
    },
    async runTask(taskId: string) {
      // Would call tasksApi.runTask(taskId)
    },
    async fetchRecentRuns() {
      try { this.recentRuns = [] } catch { /* ignore */ }
    },
    async fetchTaskRuns(taskId: string): Promise<TaskRun[]> {
      return []
    },
  },
})
