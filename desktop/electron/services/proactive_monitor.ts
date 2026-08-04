/**
 * Sprint 5 — Proactive Observer coordinator.
 *
 * Two observation sources converge here:
 *   1. FileWatcher  → fires onFileChange(workspace, file, ext) on save.
 *   2. Terminal     → polled every POLL_INTERVAL_MS for recent scrollback.
 *
 * Events are debounced (coalesced within a DEBOUNCE_MS window) and each
 * batch is sent to the backend `POST /api/proactive/check` for a small
 * LLM judgement. When the backend says it's worth a nudge, we push a
 * `proactiveObservation` IPC event to every renderer window so the
 * ProactiveToast can surface it.
 *
 * The whole subsystem is opt-in: callers pass an `enabled` getter. When
 * disabled we skip both polling and file hooks.
 */
import { BrowserWindow } from 'electron'
import { ELECTRON_EVENT_CHANNELS } from '../ipc/channels'
import { fileWatcher, FileChangeEvent } from './file_watcher'
import type { ElectronTerminalService } from './terminal'

const POLL_INTERVAL_MS = 30 * 1000 // every 30 seconds (was 5 min; shortened so the observer feels "live")
const DEBOUNCE_MS = 5_000              // coalesce bursts
const TERMINAL_MAX_CHARS = 2000

export interface ProactiveObservation {
  source: 'file' | 'terminal'
  summary: string
  suggestion: string
  workspace?: string
  timestamp: number
}

export interface ProactiveMonitorOptions {
  /** Whether the observer is enabled (read live so settings can toggle it). */
  enabled: () => boolean
  /** Whether to observe file changes (live). */
  observeFiles: () => boolean
  /** Whether to observe terminal output (live). */
  observeTerminal: () => boolean
  /** Terminal service to read scrollback from. */
  terminalService: () => ElectronTerminalService | null
  /** Base URL of the FastAPI server (for /api/proactive/check). */
  serverUrl: () => string
  /** Current workspace dir, to pass to the backend. */
  workspace: () => string
}

export class ProactiveMonitor {
  private pollTimer: NodeJS.Timeout | null = null
  private debounceTimer: NodeJS.Timeout | null = null
  private pending: Array<{ source: 'file' | 'terminal'; content: string }> = []
  private fileHandler: ((evt: FileChangeEvent) => void) | null = null
  private lastTerminalSnapshot = ''

  constructor(private readonly opts: ProactiveMonitorOptions) {}

  /** Start observing. Idempotent. */
  start(): void {
    if (this.pollTimer) return
    // Wire file changes.
    this.fileHandler = (evt) => this.onFileChange(evt)
    fileWatcher.on('change', this.fileHandler)
    // Terminal poll.
    this.pollTimer = setInterval(() => this.pollTerminal(), POLL_INTERVAL_MS)
    console.log('[proactive] monitor started')
  }

  /** Stop observing and clean up. */
  stop(): void {
    if (this.fileHandler) {
      fileWatcher.off('change', this.fileHandler)
      this.fileHandler = null
    }
    if (this.pollTimer) {
      clearInterval(this.pollTimer)
      this.pollTimer = null
    }
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer)
      this.debounceTimer = null
    }
    this.pending = []
  }

  /** Public hook so main.ts can forward fileWatcher events (or tests).
   *  P2-NS — now reads the file's tail (last 1000 chars) so the LLM
   *  judge can see actual content (e.g. a syntax error, a suspicious
   *  config value) instead of guessing from the filename alone.
   *  This closes the gap between the resume claim ("flags suspicious
   *  config") and the old implementation (only saw the filename).
   */
  onFileChange(evt: FileChangeEvent): void {
    if (!this.opts.enabled() || !this.opts.observeFiles()) return
    // Try to read the last ~1000 chars of the file for context.
    let fileTail = ''
    try {
      const fs = require('node:fs')
      const path = require('node:path')
      const fullPath = path.join(evt.workspace, evt.file)
      const stat = fs.statSync(fullPath)
      if (stat.isFile() && stat.size < 50_000) {
        // Small enough to read entirely
        fileTail = fs.readFileSync(fullPath, 'utf-8').slice(-1000)
      } else if (stat.isFile()) {
        // Large file: read last 1000 bytes
        const fd = fs.openSync(fullPath, 'r')
        const buf = Buffer.alloc(1000)
        fs.readSync(fd, buf, 0, 1000, stat.size - 1000)
        fs.closeSync(fd)
        fileTail = buf.toString('utf-8')
      }
    } catch {
      // File may have been deleted or is not readable — just use the name.
    }
    const content = fileTail
      ? `${evt.file} (${evt.ext}) changed in ${evt.workspace}\n--- file tail (last 1000 chars) ---\n${fileTail}`
      : `${evt.file} (${evt.ext}) changed in ${evt.workspace}`
    this.queue({ source: 'file', content })
  }

  /** Read the latest terminal scrollback; queue if it changed. */
  private pollTerminal(): void {
    if (!this.opts.enabled() || !this.opts.observeTerminal()) return
    const svc = this.opts.terminalService()
    if (!svc) return
    const snapshot = svc.getLatestScrollback(TERMINAL_MAX_CHARS)
    if (!snapshot || snapshot === this.lastTerminalSnapshot) return
    // Only consider the *new* tail for novelty.
    const prev = this.lastTerminalSnapshot
    this.lastTerminalSnapshot = snapshot
    const diff = prev && snapshot.startsWith(prev) ? snapshot.slice(prev.length) : snapshot
    if (!diff.trim()) return
    this.queue({ source: 'terminal', content: diff })
  }

  /** Debounced enqueue → after DEBOUNCE_MS, flush all pending to backend. */
  private queue(item: { source: 'file' | 'terminal'; content: string }): void {
    this.pending.push(item)
    if (this.debounceTimer) clearTimeout(this.debounceTimer)
    this.debounceTimer = setTimeout(() => this.flush(), DEBOUNCE_MS)
  }

  private async flush(): Promise<void> {
    const batch = this.pending.splice(0)
    this.debounceTimer = null
    if (batch.length === 0) return
    // Send each item to the backend for judgement.
    for (const item of batch) {
      try {
        const verdict = await this.checkWithBackend(item.source, item.content)
        if (verdict.worth) {
          this.broadcast({
            source: item.source,
            summary: verdict.summary,
            suggestion: verdict.suggestion,
            workspace: this.opts.workspace(),
            timestamp: Date.now(),
          })
        }
      } catch (err) {
        console.warn('[proactive] check failed:', err)
      }
    }
  }

  private async checkWithBackend(
    source: 'file' | 'terminal',
    content: string,
  ): Promise<{ worth: boolean; summary: string; suggestion: string }> {
    const base = this.opts.serverUrl().replace(/\/+$/, '')
    const url = `${base}/api/proactive/check`
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 15_000)
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source, content, workspace: this.opts.workspace() }),
        signal: controller.signal,
      })
      if (!res.ok) return { worth: false, summary: '', suggestion: '' }
      const data = (await res.json()) as { worth?: boolean; summary?: string; suggestion?: string }
      return {
        worth: !!data.worth,
        summary: data.summary ?? '',
        suggestion: data.suggestion ?? '',
      }
    } finally {
      clearTimeout(timer)
    }
  }

  private broadcast(obs: ProactiveObservation): void {
    for (const win of BrowserWindow.getAllWindows()) {
      if (!win.isDestroyed()) {
        win.webContents.send(ELECTRON_EVENT_CHANNELS.proactiveObservation, obs)
      }
    }
    // P2-NS — also raise a system-level (OS) notification so the user
    // sees the event even when MadCop is in the background / minimised.
    // Without this, the ProactiveToast (in-window) is invisible when the
    // user is in another app. The desktop notification carries the same
    // summary + suggestion; clicking it focuses the MadCop window.
    this.fireSystemNotification(obs)
  }

  private fireSystemNotification(obs: ProactiveObservation): void {
    try {
      const { Notification } = require('electron') as typeof import('electron')
      if (!Notification.isSupported()) return
      const title = obs.source === 'file' ? 'MadCop · File change' : 'MadCop · Terminal'
      const n = new Notification({
        title,
        body: obs.suggestion ? `${obs.summary} — ${obs.suggestion}` : obs.summary,
        silent: false,
      })
      n.on('click', () => {
        const win = BrowserWindow.getAllWindows().find(w => !w.isDestroyed())
        if (win) {
          if (win.isMinimized()) win.restore()
          win.focus()
        }
      })
      n.show()
    } catch (e) {
      // best-effort: never let notification failures break the observer
      console.warn('[proactive] system notification failed:', e)
    }
  }
}
