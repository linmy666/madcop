<script setup lang="ts">
/**
 * FilePreviewModal — Qoder-style delivery preview: clicking a file in
 * the completion card opens a centered overlay with the file's rendered
 * content (markdown for .md, plain text for everything else).
 *
 * Content comes from GET /api/v4/file/preview (allowlist-checked,
 * 120KB cap, binary refused). Esc / backdrop click closes.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getApiUrl } from '../../api/client'
import MarkdownRenderer from '../shared/MarkdownRenderer.vue'

const props = defineProps<{ path: string }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const loading = ref(true)
const error = ref('')
const content = ref('')
const sizeLabel = ref('')
const truncated = ref(false)

const name = computed(() => props.path.split(/[\\/]/).pop() || props.path)
const isMarkdown = computed(() => /\.md$/i.test(props.path))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch(getApiUrl(
      `/api/v4/file/preview?path=${encodeURIComponent(props.path)}`))
    const data = await res.json()
    if (!data?.ok) {
      error.value = String(data?.error || '无法读取文件')
    } else {
      content.value = String(data.content || '')
      sizeLabel.value = `${((Number(data.size) || 0) / 1024).toFixed(1)} KB`
      truncated.value = !!data.truncated
    }
  } catch (e: any) {
    error.value = String(e?.message || e || '网络错误')
  } finally {
    loading.value = false
  }
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => {
  document.addEventListener('keydown', onKey)
  void load()
})
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div class="fpm__backdrop" data-testid="file-preview-modal" @click.self="emit('close')">
      <div class="fpm" role="dialog" :aria-label="`${name} 预览`">
        <header class="fpm__head">
          <span class="fpm__icon" aria-hidden="true">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </span>
          <span class="fpm__name" :title="path">{{ name }}</span>
          <span v-if="sizeLabel" class="fpm__size">{{ sizeLabel }}<template v-if="truncated"> · 已截断</template></span>
          <button type="button" class="fpm__close" aria-label="关闭预览" @click="emit('close')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <path d="M18 6 6 18M6 6l12 12"/>
            </svg>
          </button>
        </header>
        <div class="fpm__body" data-testid="file-preview-body">
          <div v-if="loading" class="fpm__state">读取中…</div>
          <div v-else-if="error" class="fpm__state fpm__state--err">{{ error }}</div>
          <pre v-else-if="!isMarkdown" class="fpm__text">{{ content }}</pre>
          <!-- Markdown renders as styled prose when the shared renderer is
               available; falls back to plain text if not. -->
          <div v-else class="fpm__md">
            <MarkdownRenderer :content="content" variant="document" />
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.fpm__backdrop {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.32);
  animation: fpm-fade 0.14s ease-out;
}
@keyframes fpm-fade {
  from { opacity: 0; }
  to { opacity: 1; }
}
.fpm {
  display: flex;
  flex-direction: column;
  width: min(760px, 86vw);
  height: min(640px, 84vh);
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e5e5);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.18);
  overflow: hidden;
  animation: fpm-pop 0.16s ease-out;
}
@keyframes fpm-pop {
  from { opacity: 0; transform: translateY(8px) scale(0.985); }
  to { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .fpm__backdrop, .fpm { animation: none; }
}
.fpm__head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-separator, #ececec);
  background: var(--color-surface-container-lowest, #fafafa);
}
.fpm__icon { display: flex; color: var(--color-text-tertiary, #8f8f8f); }
.fpm__name {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12.5px;
  font-weight: 500;
  color: var(--color-text-primary, #0d0d0d);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fpm__size {
  flex-shrink: 0;
  font-size: 10.5px;
  color: var(--color-text-tertiary, #8f8f8f);
}
.fpm__close {
  margin-left: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-tertiary, #8f8f8f);
  cursor: pointer;
}
.fpm__close:hover {
  background: var(--color-surface-container, #f0f0f0);
  color: var(--color-text-primary, #0d0d0d);
}
.fpm__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 16px 18px;
}
.fpm__state {
  padding: 40px 0;
  text-align: center;
  font-size: 12.5px;
  color: var(--color-text-tertiary, #8f8f8f);
}
.fpm__state--err { color: var(--color-error, #dc2626); }
.fpm__text {
  margin: 0;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-primary, #0d0d0d);
  white-space: pre-wrap;
  word-break: break-word;
}
.fpm__md { font-size: 13px; line-height: 1.65; }
</style>
