<script setup lang="ts">
// v3.0 — DoctorPanel (Vue 3)
// Direct translation — same Tailwind classes, same doctor repair logic.
import { ref, computed } from 'vue'
import Button from '../shared/Button.vue'

const props = withDefaults(defineProps<{
  compact?: boolean
}>(), {
  compact: false,
})

const emit = defineEmits<{ (e: 'toast', toast: { type: string; message: string }): void }>()

const isRunning = ref(false)
const statusText = ref('')

async function handleRun() {
  isRunning.value = true
  statusText.value = ''
  try {
    const r = await fetch('/api/doctor', { method: 'POST' })
    const data = await r.json()
    if (data.local?.removedKeys) {
      statusText.value = `清理了 ${data.local.removedKeys.length} 个无效 key。`
      emit('toast', { type: data.local.failedKeys?.length ? 'warning' : 'success', message: statusText.value })
    }
  } catch (e: any) {
    emit('toast', { type: 'error', message: e?.message || '诊断失败' })
  } finally {
    isRunning.value = false
  }
}
</script>

<template>
  <section :class="['rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]', compact ? 'p-3' : 'p-4']">
    <div :class="['flex', compact ? 'flex-col gap-3' : 'items-start justify-between gap-4']">
      <div class="min-w-0">
        <div class="text-sm font-medium text-[var(--color-text-primary)]">环境诊断</div>
        <p class="mt-1 text-xs text-[var(--color-text-tertiary)]">
          运行诊断以清理过期的 API key 缓存和无效配置。
        </p>
        <p class="mt-1 text-xs text-[var(--color-text-tertiary)]">
          诊断不会触碰你的加密数据或聊天记录。
        </p>
      </div>
      <div :class="['flex', compact ? 'justify-start' : 'justify-end', 'shrink-0']">
        <Button size="sm" :loading="isRunning" @click="handleRun">
          <template #icon><span class="material-symbols-outlined text-[16px]">stethoscope</span></template>
          运行诊断
        </Button>
      </div>
    </div>
    <div class="mt-2 text-[11px] leading-relaxed text-[var(--color-text-tertiary)]">
      安全清理: API key 缓存、Provider 过期配置、WebSocket 断连残留。
    </div>
    <div v-if="statusText" class="mt-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-container)] px-2.5 py-2 text-xs text-[var(--color-text-secondary)]">
      {{ statusText }}
    </div>
  </section>
</template>
