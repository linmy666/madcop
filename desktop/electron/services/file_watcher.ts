/**
 * Sprint 5 — File watcher skeleton.
 *
 * Watches a workspace directory for file changes and emits
 * `proactive:file-change` IPC events. The full pipeline (debounce,
 * LLM analysis, notification) is left as a follow-up — this
 * scaffold wires up the watch + IPC plumbing.
 */
import * as fs from 'node:fs'
import * as path from 'node:path'
import { EventEmitter } from 'node:events'
import { BrowserWindow } from 'electron'

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
  private watchers: Map<string, fs.FSWatcher> = new Map()
  private pending: Map<string, NodeJS.Timeout> = new Map()

  watch(workspace: string): void {
    if (this.watchers.has(workspace)) return
    try {
      // recursive: true captures changes in subdirectories too — essential
      // because real code lives under madcop/, desktop/, etc. Supported on
      // macOS (FSEvents), Windows, and Linux (Node 22+ inotify).
      const watcher = fs.watch(workspace, { recursive: true }, (_event, filename) => {
        if (!filename) return
        // filename may be a relative path like "madcop/agent/creation.py"
        const basename = path.basename(filename)
        const ext = path.extname(basename).toLowerCase()
        if (!SUPPORTED_EXTS.has(ext)) return
        this.debouncedEmit(workspace, filename, ext)
      })
      watcher.on('error', (err) => {
        console.warn('[file_watcher] watch error:', err.message)
      })
      this.watchers.set(workspace, watcher)
      console.log(`[file_watcher] watching ${workspace} (recursive)`)
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
      // Broadcast to renderer windows (legacy channel)...
      for (const win of BrowserWindow.getAllWindows()) {
        win.webContents.send('proactive:file-change', evt)
      }
      // ...and to in-process listeners (the ProactiveMonitor coordinator).
      this.emit('change', evt)
    }, DEBOUNCE_MS))
  }

  unwatch(workspace: string): void {
    const w = this.watchers.get(workspace)
    if (w) {
      w.close()
      this.watchers.delete(workspace)
    }
  }

  dispose(): void {
    for (const w of this.watchers.values()) w.close()
    this.watchers.clear()
    for (const t of this.pending.values()) clearTimeout(t)
    this.pending.clear()
  }
}

export const fileWatcher = new FileWatcher()
