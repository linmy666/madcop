<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { getApiUrl } from '../../api/client'

const props = defineProps<{
  refreshKey?: number
}>()

const previewUrl = ref(getApiUrl('/preview/'))
const loading = ref(true)
const error = ref<string | null>(null)

// Reload the iframe with a cache-busting query param. Called on mount,
// on manual refresh, and when refreshKey changes (driven by the
// preview_update SSE event — no more 2s polling that caused flicker).
function reloadPreview() {
  loading.value = true
  error.value = null
  previewUrl.value = getApiUrl('/preview/') + '?t=' + Date.now()
}

onMounted(() => {
  reloadPreview()
})

// Refresh when the backend signals a preview_update (AI wrote a file),
// or when the user clicks the refresh button.
watch(() => props.refreshKey, () => {
  reloadPreview()
})

function handleIframeLoad() {
  loading.value = false
}

function handleIframeError() {
  error.value = '预览加载失败'
  loading.value = false
}

function openInBrowser() {
  window.open(previewUrl.value, '_blank')
}
</script>

<template>
  <div class="preview-panel">
    <!-- Toolbar -->
    <div class="preview-toolbar">
      <div class="preview-toolbar__left">
        <span class="preview-label">实时预览</span>
        <span class="preview-url" :title="previewUrl">{{ previewUrl }}</span>
      </div>
      <div class="preview-toolbar__right">
        <button
          @click="reloadPreview"
          class="preview-btn"
          title="刷新"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
            <path d="M1 4v6h6M23 20v-6h-6"/>
            <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
          </svg>
        </button>
        <button
          @click="openInBrowser"
          class="preview-btn"
          title="浏览器打开"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
            <polyline points="15 3 21 3 21 9"/>
            <line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Iframe -->
    <div class="preview-iframe-container">
      <div v-if="loading" class="preview-loading">
        <div class="preview-loading-dot"></div>
      </div>
      <div v-if="error" class="preview-error">{{ error }}</div>
      <iframe
        :src="previewUrl"
        class="preview-iframe"
        sandbox="allow-scripts allow-same-origin"
        @load="handleIframeLoad"
        @error="handleIframeError"
      ></iframe>
    </div>
  </div>
</template>

<style scoped>
.preview-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background: var(--color-surface, #fff);
}

.preview-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  border-bottom: 1px solid var(--color-border, #e5e5e5);
  background: var(--color-surface-container, #f5f5f5);
  flex-shrink: 0;
  min-height: 36px;
}

.preview-toolbar__left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.preview-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary, #666);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.preview-url {
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--color-text-tertiary, #999);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preview-toolbar__right {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.preview-btn {
  padding: 4px 6px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--color-text-secondary, #666);
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: background 0.1s, color 0.1s;
}
.preview-btn:hover {
  background: var(--color-surface-container-high, #e8e8e8);
  color: var(--color-text-primary, #222);
}
.preview-btn:active { opacity: 0.7; }

.preview-iframe-container {
  flex: 1;
  position: relative;
  overflow: hidden;
  background: #fff;
}

.preview-iframe {
  width: 100%;
  height: 100%;
  min-height: 600px; /* ensure the iframe is tall enough for typical
                       * preview pages (login forms, dashboards) so
                       * the bottom isn't clipped off. */
  border: none;
  display: block;
}

.preview-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.7);
  z-index: 10;
}

.preview-loading-dot {
  width: 20px;
  height: 20px;
  border: 2px solid var(--color-border, #e5e5e5);
  border-top-color: var(--color-brand, #333);
  border-radius: 50%;
  animation: preview-spin 0.8s linear infinite;
}

@keyframes preview-spin {
  to { transform: rotate(360deg); }
}

.preview-error {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--color-danger, #e00);
  z-index: 10;
}
</style>