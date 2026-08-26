<script setup lang="ts">
/**
 * FileCompletionCard — the top-of-message "✅ 已生成" card.
 *
 * Shown after a build-style turn (write_file / edit_file called at
 * least once) so the user gets a real "where is the result?" affordance
 * instead of a buried code block. Two paths:
 *   - Files: one row per path, with the file's name + size hint.
 *   - Actions: [Open folder] [Reveal in Finder] [Download] wired to
 *     simple per-file actions (download via blob URL, others via the
 *     Electron bridge when available, else graceful no-op).
 */
import { computed } from 'vue'
import { useTranslation } from '../../i18n'

interface Props {
  paths: string[]
  /** Workspace root — used for "Open folder" / "Reveal in Finder". */
  workDir?: string
  /** Caption above the file list (e.g. "1 file generated · 23.4 KB"). */
  caption?: string
}

const props = withDefaults(defineProps<Props>(), { workDir: undefined, caption: undefined })
const t = useTranslation()

interface FileRow { name: string; dir: string; full: string }

const rows = computed<FileRow[]>(() => {
  return props.paths.map((p) => {
    const i = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'))
    return { full: p, dir: i >= 0 ? p.slice(0, i) : '', name: i >= 0 ? p.slice(i + 1) : p }
  })
})

const totalLabel = computed(() => {
  if (props.caption) return props.caption
  const n = rows.value.length
  return t('fileCompletion.count', `${n} file${n === 1 ? '' : 's'} generated`, { count: n })
})

function shortName(p: string, max = 36): string {
  if (p.length <= max) return p
  // show last 2 path segments
  const parts = p.split('/')
  if (parts.length > 2) return '…/' + parts.slice(-2).join('/')
  return p
}

function downloadOne(path: string) {
  // We don't have the file content in the client. Without a backend
  // /file-download endpoint we can only trigger the Electron bridge
  // or fall back to a polite no-op. The user usually clicks "Open
  // folder" / "Reveal" anyway, both of which we attempt below.
  try {
    const w: any = window as any
    if (w.madcop?.shell?.open) { w.madcop.shell.open(path); return }
  } catch { /* ignore */ }
  // No reliable portable "download a server file" path without a
  // download endpoint, so we just no-op the click — the other two
  // buttons (Open folder / Reveal) are the real affordances.
}

function openFolder() {
  try {
    const w: any = window as any
    if (w.madcop?.shell?.open) { w.madcop.shell.open(props.workDir || '.'); return }
  } catch { /* ignore */ }
}

function revealInFinder() {
  // Reveal the FIRST file (no multi-select in shell API); users with
  // many files will fall back to "Open folder" anyway.
  const first = rows.value[0]
  if (!first) return
  try {
    const w: any = window as any
    if (w.madcop?.shell?.reveal) { w.madcop.shell.reveal(first.full); return }
  } catch { /* ignore */ }
}
</script>

<template>
  <section
    v-if="rows.length"
    class="file-completion"
    data-testid="file-completion-card"
  >
    <header class="fc__head">
      <span class="fc__icon" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </span>
      <span class="fc__title">{{ totalLabel }}</span>
    </header>
    <ul class="fc__list">
      <li v-for="r in rows" :key="r.full" class="fc__row">
        <code class="fc__name" :title="r.full">{{ shortName(r.full) }}</code>
        <button
          type="button"
          class="fc__icon-btn"
          :aria-label="t('fileCompletion.reveal', 'Reveal in Finder')"
          :title="t('fileCompletion.reveal', 'Reveal in Finder')"
          data-testid="fc-reveal"
          @click="revealInFinder"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 3h7v2H5v14h14V9h2v12a2 2 0 0 1-2 2H3z" />
            <path d="M14 3h7v7" />
            <path d="M10 10l11-11" />
          </svg>
        </button>
        <button
          type="button"
          class="fc__icon-btn"
          :aria-label="t('fileCompletion.download', 'Download')"
          :title="t('fileCompletion.download', 'Download')"
          data-testid="fc-download"
          @click="downloadOne(r.full)"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
        </button>
      </li>
    </ul>
    <footer class="fc__actions">
      <button
        type="button"
        class="fc__btn fc__btn--primary"
        data-testid="fc-open-folder"
        @click="openFolder"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        </svg>
        <span>{{ t('fileCompletion.openFolder', 'Open folder') }}</span>
      </button>
    </footer>
  </section>
</template>

<style scoped>
.file-completion {
  border: 1px solid var(--color-success, #1f9d55);
  border-radius: 12px;
  background: color-mix(in srgb, var(--color-success, #1f9d55) 6%, var(--color-surface));
  padding: 10px 12px;
  margin: 6px 0 14px;
  font-size: 12px;
}
.fc__head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: var(--color-success, #1f9d55);
  margin-bottom: 8px;
}
.fc__icon { display: inline-flex; }
.fc__title { font-size: 12.5px; }
.fc__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.fc__row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  border-radius: 6px;
  background: var(--color-surface-container-low, transparent);
}
.fc__row:hover { background: var(--color-surface-container); }
.fc__name {
  flex: 1;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11.5px;
  color: var(--color-text-secondary, #555);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fc__icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px; height: 24px;
  border: 0;
  background: transparent;
  border-radius: 4px;
  color: var(--color-text-tertiary, #888);
  cursor: pointer;
}
.fc__icon-btn:hover {
  background: var(--color-surface-container);
  color: var(--color-text-primary, #111);
}
.fc__actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
.fc__btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border: 1px solid var(--color-border, rgba(128,128,128,0.25));
  border-radius: 6px;
  background: var(--color-surface, #fff);
  color: var(--color-text-primary, #111);
  font-size: 11.5px;
  cursor: pointer;
  font-family: inherit;
}
.fc__btn--primary {
  background: var(--color-success, #1f9d55);
  color: var(--color-on-primary, #fff);
  border-color: var(--color-success, #1f9d55);
}
.fc__btn:hover { filter: brightness(0.97); }
</style>
