import { defineStore } from 'pinia'
import { tasksApi } from '../api/tasks'
import type { CronTask, CreateTaskInput, TaskRun } from '../../types/task'

/**
 * Scheduled/cron tasks — wired to /api/scheduled-tasks.
 */

export type { CronTask, TaskRun }

function normalizeTask(raw: any): CronTask {
  return {
    id: String(raw?.id ?? ''),
    name: raw?.name || 'Untitled task',
    description: raw?.description,
    cron: raw?.cron || raw?.schedule || '*/5 * * * *',
    prompt: raw?.prompt || '',
    enabled: raw?.enabled !== false,
    recurring: raw?.recurring,
    permanent: raw?.permanent,
    createdAt: typeof raw?.createdAt === 'number'
      ? raw.createdAt
      : Date.parse(raw?.createdAt || '') || Date.now(),
    lastRunAt: raw?.lastRunAt,
    lastFiredAt: raw?.lastFiredAt,
    nextRunAt: raw?.nextRunAt,
    permissionMode: raw?.permissionMode,
    model: raw?.model,
    providerId: raw?.providerId,
    folderPath: raw?.folderPath,
    useWorktree: raw?.useWorktree,
    notification: raw?.notification,
  }
}

function normalizeRun(raw: any): TaskRun {
  return {
    id: String(raw?.id ?? ''),
    taskId: String(raw?.taskId ?? raw?.task_id ?? ''),
    taskName: raw?.taskName || raw?.name || '',
    startedAt: raw?.startedAt || new Date().toISOString(),
    completedAt: raw?.completedAt || raw?.finishedAt,
    status: (raw?.status || 'completed') as TaskRun['status'],
    prompt: raw?.prompt || '',
    output: raw?.output,
    error: raw?.error,
    exitCode: raw?.exitCode,
    durationMs: raw?.durationMs,
    sessionId: raw?.sessionId,
  }
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
        const data = await tasksApi.list()
        const list = Array.isArray((data as any)?.tasks) ? (data as any).tasks : []
        this.tasks = list.map(normalizeTask)
      } catch (err) {
        this.error = (err as Error).message
        this.tasks = []
      } finally {
        this.isLoading = false
      }
    },

    async createTask(input: CreateTaskInput | any) {
      try {
        const data = await tasksApi.create({
          name: input.name || 'New Task',
          cron: input.cron || input.schedule || '0 9 * * *',
          prompt: input.prompt || '',
          enabled: input.enabled !== false,
          description: input.description,
          recurring: input.recurring,
          permanent: input.permanent,
          permissionMode: input.permissionMode,
          model: input.model,
          providerId: input.providerId,
          folderPath: input.folderPath,
          useWorktree: input.useWorktree,
          notification: input.notification,
        })
        const task = normalizeTask((data as any)?.task || data)
        this.tasks.unshift(task)
        return task
      } catch (err) {
        this.error = (err as Error).message
        throw err
      }
    },

    async updateTask(id: string, updates: Partial<CronTask>) {
      try {
        const data = await tasksApi.update(id, updates as any)
        const task = normalizeTask((data as any)?.task || { id, ...updates })
        const idx = this.tasks.findIndex((t) => t.id === id)
        if (idx >= 0) this.tasks[idx] = { ...this.tasks[idx], ...task }
        return task
      } catch (err) {
        // Optimistic local update if API flaky
        const idx = this.tasks.findIndex((t) => t.id === id)
        if (idx >= 0) Object.assign(this.tasks[idx], updates)
        this.error = (err as Error).message
      }
    },

    async deleteTask(id: string) {
      try {
        await tasksApi.delete(id)
      } catch (err) {
        this.error = (err as Error).message
      }
      this.tasks = this.tasks.filter((t) => t.id !== id)
    },

    async runTask(taskId: string) {
      try {
        const data = await tasksApi.runTask(taskId)
        const run = normalizeRun((data as any)?.run || data)
        this.recentRuns.unshift(run)
        return run
      } catch (err) {
        this.error = (err as Error).message
        throw err
      }
    },

    async fetchRecentRuns() {
      try {
        const data = await tasksApi.getRecentRuns(50)
        const list = Array.isArray((data as any)?.runs) ? (data as any).runs : []
        this.recentRuns = list.map(normalizeRun)
      } catch {
        this.recentRuns = []
      }
    },

    async fetchTaskRuns(taskId: string): Promise<TaskRun[]> {
      try {
        const data = await tasksApi.getTaskRuns(taskId)
        const list = Array.isArray((data as any)?.runs) ? (data as any).runs : []
        return list.map(normalizeRun)
      } catch {
        return []
      }
    },
  },
})
