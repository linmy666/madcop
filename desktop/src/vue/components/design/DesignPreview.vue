<script setup lang="ts">
/**
 * DesignPreview — render DesignData as an iframe preview (not chat /preview/).
 */
import { computed, watch, ref } from 'vue'
import type { DesignData } from '../../lib/designJson'
import { designDataToHtml } from '../../lib/designRender'

const props = defineProps<{
  data: DesignData | null
}>()

const html = computed(() => designDataToHtml(props.data))

const srcdoc = ref(html.value)
watch(html, (h) => {
  srcdoc.value = h
}, { immediate: true })
</script>

<template>
  <div class="dprev">
    <div class="dprev__bar">
      <span class="dprev__label">设计预览</span>
      <span class="dprev__hint">当前页面 HTML（非聊天 /preview/）</span>
    </div>
    <iframe
      class="dprev__frame"
      title="design-preview"
      sandbox="allow-same-origin"
      :srcdoc="srcdoc"
    />
  </div>
</template>

<style scoped>
.dprev {
  display: flex;
  flex-direction: column;
  height: 280px;
  flex-shrink: 0;
  border-top: 1px solid var(--color-border);
  background: var(--color-surface-container-low);
}
.dprev__bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.dprev__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.dprev__hint {
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.dprev__frame {
  flex: 1;
  width: 100%;
  border: none;
  background: #fff;
}
</style>
