// v3.0 — Pinia updateStore (mirrors React zustand useUpdateStore)
// Handles app update checking, downloading, and installation.
import { defineStore } from 'pinia'
import { getDesktopHost } from '../../lib/desktopHost'
import type { DesktopHost, DesktopUpdate } from '../../lib/desktopHost'
import type { UpdateProxySettings } from '../../types/settings'
import { useSettingsStore } from './settingsStore'

export type UpdateStatus =
  | 'idle'
  | 'checking'
  | 'available'
  | 'up-to-date'
  | 'downloading'
  | 'downloaded'
  | 'installing'
  | 'restarting'
  | 'error'

const DISMISSED_UPDATE_VERSION_KEY = 'madcop-agent-dismissed-update-version'

type UpdateState = {
  status: UpdateStatus
  availableVersion: string | null
  releaseNotes: string | null
  progressPercent: number
  downloadedBytes: number
  totalBytes: number | null
  error: string | null
  checkedAt: number | null
  shouldPrompt: boolean
}

let pendingUpdate: DesktopUpdate | null = null
let pendingUpdateProxyKey: string | null = null
let pendingUpdateDownloaded = false
let downloadPromise: Promise<void> | null = null
let downloadingProxyKey: string | null = null
let startupCheckPromise: Promise<void> | null = null

function readDismissedUpdateVersion(): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(DISMISSED_UPDATE_VERSION_KEY)
  } catch {
    return null
  }
}

function writeDismissedUpdateVersion(version: string | null) {
  if (typeof window === 'undefined') return
  try {
    if (version) {
      window.localStorage.setItem(DISMISSED_UPDATE_VERSION_KEY, version)
    } else {
      window.localStorage.removeItem(DISMISSED_UPDATE_VERSION_KEY)
    }
  } catch {
    // Ignore storage write failures.
  }
}

function getUpdateProxyUrl(settings?: UpdateProxySettings): string | null {
  const s = settings ?? useSettingsStore().updateProxy
  if (s.mode !== 'manual') return null
  const proxy = s.url.trim()
  return proxy || null
}

function getUpdateProxyKey(settings?: UpdateProxySettings): string {
  const proxy = getUpdateProxyUrl(settings)
  return proxy ? `manual:${proxy}` : 'system'
}

function getUpdateCheckOptions(): { proxy: string } | undefined {
  const proxy = getUpdateProxyUrl()
  return proxy ? { proxy } : undefined
}

function getUpdateHost(): DesktopHost | null {
  const host = getDesktopHost()
  return host.capabilities.updates ? host : null
}

async function setPendingUpdate(next: DesktopUpdate | null, proxyKey: string | null) {
  const previous = pendingUpdate
  pendingUpdate = next
  pendingUpdateProxyKey = next ? proxyKey : null
  pendingUpdateDownloaded = false
  if (!downloadPromise) {
    downloadingProxyKey = null
  }

  if (previous && previous !== next) {
    try {
      await previous.close()
    } catch {
      // Ignore stale resource cleanup failures.
    }
  }
}

function shouldPromptForVersion(version: string | null) {
  return !!version && readDismissedUpdateVersion() !== version
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function parseAppVersion(version: string | null | undefined): [number, number, number] | null {
  const match = version?.trim().replace(/^v/i, '').match(/^(\d+)\.(\d+)\.(\d+)/)
  if (!match) return null
  return match.slice(1).map(Number) as [number, number, number]
}

function compareAppVersions(left: string | null | undefined, right: string | null | undefined): number | null {
  const leftParts = parseAppVersion(left)
  const rightParts = parseAppVersion(right)
  if (!leftParts || !rightParts) return null

  for (let index = 0; index < leftParts.length; index += 1) {
    const delta = leftParts[index]! - rightParts[index]!
    if (delta !== 0) return delta
  }
  return 0
}

function isUpdateNewerThanCurrent(updateVersion: string, currentVersion: string | null): boolean {
  const comparison = compareAppVersions(updateVersion, currentVersion)
  return comparison === null || comparison > 0
}

async function getCurrentAppVersion(host: DesktopHost): Promise<string | null> {
  try {
    return await host.app.getVersion()
  } catch {
    return null
  }
}

async function closeIgnoredUpdate(update: DesktopUpdate) {
  try {
    await update.close()
  } catch {
    // Best effort: a stale same-version update should not keep the prompt alive.
  }
}

export const useUpdateStore = defineStore('update', {
  state: (): UpdateState => ({
    status: 'idle',
    availableVersion: null,
    releaseNotes: null,
    progressPercent: 0,
    downloadedBytes: 0,
    totalBytes: null,
    error: null,
    checkedAt: null,
    shouldPrompt: false,
  }),

  actions: {
    async initialize() {
      if (!getUpdateHost()) return
      if (!startupCheckPromise) {
        startupCheckPromise = (async () => {
          await new Promise((resolve) => setTimeout(resolve, 5000))
          await this.checkForUpdates({ silent: true })
        })().finally(() => {
          startupCheckPromise = null
        })
      }
      await startupCheckPromise
    },

    async checkForUpdates({ silent = false, autoDownload = true } = {}): Promise<DesktopUpdate | null> {
      const host = getUpdateHost()
      if (!host) return null
      if (downloadPromise && this.status === 'downloading' && pendingUpdate) return pendingUpdate

      this.status = 'checking'
      this.error = null

      try {
        const updateProxyKey = getUpdateProxyKey()
        const update = await host.updates.check(getUpdateCheckOptions())

        if (update && !isUpdateNewerThanCurrent(update.version, await getCurrentAppVersion(host))) {
          await closeIgnoredUpdate(update)
          await setPendingUpdate(null, null)

          const checkedAt = Date.now()
          writeDismissedUpdateVersion(null)
          Object.assign(this, {
            status: 'up-to-date',
            availableVersion: null,
            releaseNotes: null,
            progressPercent: 0,
            downloadedBytes: 0,
            totalBytes: null,
            checkedAt,
            error: null,
            shouldPrompt: false,
          })
          return null
        }

        await setPendingUpdate(update, updateProxyKey)

        const checkedAt = Date.now()

        if (!update) {
          writeDismissedUpdateVersion(null)
          Object.assign(this, {
            status: 'up-to-date',
            availableVersion: null,
            releaseNotes: null,
            progressPercent: 0,
            downloadedBytes: 0,
            totalBytes: null,
            checkedAt,
            error: null,
            shouldPrompt: false,
          })
          return null
        }

        const dismissedVersion = readDismissedUpdateVersion()
        const shouldOffer = dismissedVersion !== update.version

        Object.assign(this, {
          status: 'available',
          availableVersion: update.version,
          releaseNotes: update.body ?? null,
          progressPercent: 0,
          downloadedBytes: 0,
          totalBytes: null,
          checkedAt,
          error: null,
          shouldPrompt: false,
        })

        if (autoDownload && (shouldOffer || !silent)) {
          void this.downloadUpdate().catch(() => {
            // The store records the failure and keeps the manual install path retryable.
          })
        }
        return update
      } catch (error) {
        if (!silent) {
          Object.assign(this, {
            status: 'error',
            error: getErrorMessage(error),
            checkedAt: Date.now(),
          })
        } else {
          Object.assign(this, {
            status: this.availableVersion ? 'available' : 'idle',
            checkedAt: Date.now(),
          })
        }
        return null
      }
    },

    async downloadUpdate(): Promise<void> {
      if (!getUpdateHost()) return

      let update = pendingUpdate
      if (update && pendingUpdateProxyKey !== getUpdateProxyKey()) {
        await setPendingUpdate(null, null)
        update = null
      }
      if (!update) {
        update = await this.checkForUpdates({ autoDownload: false })
        if (!update) return
      }

      if (pendingUpdateDownloaded) {
        Object.assign(this, {
          status: 'downloaded',
          progressPercent: 100,
          shouldPrompt: shouldPromptForVersion(this.availableVersion),
        })
        return
      }

      if (downloadPromise) {
        await downloadPromise
        return
      }

      Object.assign(this, {
        status: 'downloading',
        error: null,
        shouldPrompt: false,
        progressPercent: 0,
        downloadedBytes: 0,
        totalBytes: null,
      })

      const downloadingUpdate = update
      downloadingProxyKey = pendingUpdateProxyKey
      const activeDownload = (async () => {
        let totalBytes: number | null = null
        let downloadedBytes = 0

        await downloadingUpdate.download((event) => {
          if (event.event === 'Started') {
            totalBytes = event.data.contentLength ?? null
            downloadedBytes = 0
            Object.assign(this, {
              totalBytes,
              downloadedBytes: 0,
              progressPercent: 0,
            })
          } else if (event.event === 'Progress') {
            downloadedBytes += event.data.chunkLength
            const progressPercent =
              totalBytes && totalBytes > 0
                ? Math.min(Math.round((downloadedBytes / totalBytes) * 100), 100)
                : 0

            Object.assign(this, {
              downloadedBytes,
              totalBytes,
              progressPercent,
            })
          } else if (event.event === 'Finished') {
            Object.assign(this, {
              progressPercent: 100,
            })
          }
        })

        if (pendingUpdate !== downloadingUpdate) return
        if (getUpdateProxyKey() !== downloadingProxyKey) {
          await setPendingUpdate(null, null)
          Object.assign(this, {
            status: 'available',
            progressPercent: 0,
            shouldPrompt: false,
          })
          return
        }

        pendingUpdateDownloaded = true
        Object.assign(this, {
          status: 'downloaded',
          error: null,
          shouldPrompt: shouldPromptForVersion(this.availableVersion),
          progressPercent: 100,
        })
      })()
      downloadPromise = activeDownload

      try {
        await downloadPromise
      } catch (error) {
        if (pendingUpdate === downloadingUpdate) {
          Object.assign(this, {
            status: 'available',
            error: getErrorMessage(error),
            shouldPrompt: false,
          })
        }
        throw error
      } finally {
        if (downloadPromise === activeDownload) {
          downloadPromise = null
          downloadingProxyKey = null
        }
      }
    },

    async installUpdate(): Promise<void> {
      const host = getUpdateHost()
      if (!host) return

      let update = pendingUpdate
      if (update && pendingUpdateProxyKey !== getUpdateProxyKey()) {
        await setPendingUpdate(null, null)
        update = null
      }
      if (!update) {
        update = await this.checkForUpdates({ autoDownload: false })
        if (!update) return
      }

      let prepareInstallAttempted = false
      try {
        writeDismissedUpdateVersion(null)
        if (!pendingUpdateDownloaded) {
          await this.downloadUpdate()
        }
        if (!pendingUpdateDownloaded) return

        Object.assign(this, {
          status: 'installing',
          error: null,
          shouldPrompt: false,
          progressPercent: 100,
        })

        prepareInstallAttempted = true
        await host.updates.prepareInstall()
        await update.install()

        Object.assign(this, {
          status: 'restarting',
          progressPercent: 100,
        })

        await host.updates.relaunch()
      } catch (error) {
        if (prepareInstallAttempted) {
          try {
            await host.updates.cancelInstall()
          } catch {
            // Best effort: keep the update prompt recoverable even if native reset fails.
          }
        }
        Object.assign(this, {
          status: pendingUpdateDownloaded ? 'downloaded' : 'available',
          error: getErrorMessage(error),
          shouldPrompt: true,
        })
      }
    },

    dismissPrompt() {
      writeDismissedUpdateVersion(this.availableVersion)
      this.shouldPrompt = false
    },
  },
})
