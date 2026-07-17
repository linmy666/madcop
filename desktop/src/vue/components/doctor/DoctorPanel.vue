<script setup lang="ts">
// DoctorPanel — runs /api/doctor/report and optional repair via Vue API client.
import { ref } from 'vue'
import Button from '../shared/Button.vue'
import { doctorApi } from '../../api/doctor'

const props = withDefaults(defineProps<{
  compact?: boolean
}>(), {
  compact: false,
})

const emit = defineEmits<{ (e: 'toast', toast: { type: string; message: string }): void }>()

const isRunning = ref(false)
const statusText = ref('')
const summary = ref<{ total?: number; missingCount?: number; invalidCount?: number } | null>(null)

async function handleRun() {
  isRunning.value = true
  statusText.value = ''
  summary.value = null
  try {
    const data = await doctorApi.report()
    const report = (data as any)?.report || data
    const s = report?.summary || {}
    summary.value = s
    const missing = s.missingCount ?? 0
    const invalid = s.invalidCount ?? 0
    const total = s.total ?? (report?.items?.length ?? 0)
    statusText.value =
      invalid > 0 || missing > 0
        ? `检查 ${total} 项：缺失 ${missing}，异常 ${invalid}`
        : `检查 ${total} 项，一切正常`
    emit('toast', {
      type: invalid > 0 ? 'error' : missing > 0 ? 'info' : 'success',
      message: statusText.value,
    })
    // Best-effort dry-run repair when there are issues
    if (invalid > 0 || missing > 0) {
      try {
        await doctorApi.repair()
      } catch { /* repair optional */ }
    }
  } catch (e: any) {
    statusText.value = e?.message || '诊断失败'
    emit('toast', { type: 'error', message: statusText.value })
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
          运行诊断以检查配置文件完整性，并清理无效缓存项。
        </p>
        <p class="mt-1 text-xs text-[var(--color-text-tertiary)]">
          诊断不会触碰你的加密数据或聊天记录。
        </p>
        <p v-if="statusText" class="mt-2 text-xs text-[var(--color-text-secondary)]">
          {{ statusText }}
        </p>
      </div>
      <div :class="['flex', compact ? 'justify-start' : 'justify-end', 'shrink-0']">
        <Button size="sm" :loading="isRunning" @click="handleRun">
          <template #icon><span class="material-symbols-outlined text-[16px]">stethoscope</span></template>
          {{ isRunning ? '诊断中…' : '运行诊断' }}
        </Button>
      </div>
    </div>
  </section>
</template>
