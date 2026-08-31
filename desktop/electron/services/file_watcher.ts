/**
 * Sprint 5 — File watcher skeleton.
 *
 * Watches a workspace directory for file changes and emits
 * `proactive:file-change` IPC events. The full pipeline (debounce,
 * LLM analysis, notification) is left as a follow-up — this
 * scaffold wires up the watch + IPC plumbing.
 */
import * as path from 'node:path'
import { EventEmitter } from 'node:events'
import { BrowserWindow } from 'electron'
// P2: chokidar is reliable cross-platform (macOS FSEvents, Linux
// inotify, Windows ReadDirectoryChangesW) — the bare `fs.watch`
// path was emitting zero events for write/create on /tmp on macOS.
import chokidar, { FSWatcher } from 'chokidar'

export interface FileChangeEvent {
  type: 'proactive:file-change'
  workspace: string
  file: string
  ext: string
  timestamp: number
}

const DEBOUNCE_MS = 500
const SUPPORTED_EXTS = new Set(['.py', '.ts', '.js', '.vue', '.md', '.json', '.yaml', '.yml', '.sh', '.tsx', '.jsx', '.go', '.rs', '.css', '.html'])

export class FileWatcher extends EventEmitter {
  private watchers: Map<string, FSWatcher> = new Map()
  private pending: Map<string, NodeJS.Timeout> = new Map()

  watch(workspace: string): void {
    if (this.watchers.has(workspace)) return
    try {
      // Chokidar normalizes the recursive option across platforms
      // (FSEvents on macOS didn't reliably bubble up write events for
      // symlinked roots like /private/tmp → /tmp, which silently
      // broke the proactive observer end-to-end).
      const watcher = chokidar.watch(workspace, {
        ignored: (p: string) => {
          if (p === workspace) return false
          const base = path.basename(p)
          if (base.startsWith('.') && base !== '.') return true
          if (base === 'node_modules' || base === '__pycache__') return true
          return false
        },
        ignoreInitial: true,
        persistent: false,
        depth: 8,
        awaitWriteFinish: { stabilityThreshold: 200, pollInterval: 50 },
      })
      const onEvent = (rel: string) => {
        const basename = path.basename(rel)
        const ext = path.extname(basename).toLowerCase()
        if (!SUPPORTED_EXTS.has(ext)) return
        this.debouncedEmit(workspace, rel, ext)
      }
      watcher.on('add', (p: string) => onEvent(path.relative(workspace, p) || p))
      watcher.on('change', (p: string) => onEvent(path.relative(workspace, p) || p))
      watcher.on('error', (err: unknown) => {
        console.warn('[file_watcher] chokidar error:', String(err))
      })
      this.watchers.set(workspace, watcher)
      console.log(`[file_watcher] watching ${workspace} (chokidar)`)
    } catch (err) {
      console.warn('[file_watcher] failed to start watching:', workspace, err)
    }
  }

  private debouncedEmit(workspace: string, filename: string, ext: string) {
    const key = `${workspace}::${filename}`
    const existing = this.pending.get(key)
    if (existing) clearTimeout(existing)
    this.pending.set(key, setTimeout(() => {
      this.pending.delete(key)
      const evt: FileChangeEvent = {
        type: 'proactive:file-change',
        workspace, file: filename, ext, timestamp: Date.now(),
      }
      for (const win of BrowserWindow.getAllWindows()) {
        win.webContents.send('proactive:file-change', evt)
      }
      this.emit('change', evt)
      console.log(`[file_watcher] change: ${filename}`)
    }, DEBOUNCE_MS))
  }

  async unwatch(workspace: string): Promise<void> {
    const w = this.watchers.get(workspace)
    if (w) {
      try { await w.close() } catch { /* ignore */ }
      this.watchers.delete(workspace)
    }
  }

  async dispose(): Promise<void> {
    for (const w of this.watchers.values()) {
      try { await w.close() } catch { /* ignore */ }
    }
    this.watchers.clear()
    for (const t of this.pending.values()) clearTimeout(t)
    this.pending.clear()
  }
}

export const fileWatcher = new FileWatcher()
