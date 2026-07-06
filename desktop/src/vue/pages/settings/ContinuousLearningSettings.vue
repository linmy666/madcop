<script setup lang="ts">
/**
 * ContinuousLearningSettings — local-only learning preferences.
 *
 * MadCop has NO cloud. Everything stays on the user's Mac.
 * 3 modes: 不学习 / 本地微调 / (云端不可用 — 灰显提示"纯本地")
 *
 * The feedback data collected here feeds into the offline LoRA training pipeline
 * (madcop/training/local_lora.py), which runs entirely on-device.
 */

import { ref, onMounted } from 'vue'

// ─── State ─────────────────────────────────────────────────────────────

type LearningMode = 'none' | 'local'

const mode = ref<LearningMode>('none')
const stats = ref({ total: 0, used: 0, lastTrain: null as string | null })
const trainingHistory = ref<TrainingRecord[]>([])
const loading = ref(false)

interface TrainingRecord {
  id: string
  date: string
  samples: number
  duration: string
  loss: number
  status: 'completed' | 'failed'
}

// ─── Actions ───────────────────────────────────────────────────────────

async function saveMode(newMode: LearningMode) {
  mode.value = newMode
  try {
    await fetch('/api/training/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: newMode }),
    })
  } catch {
    // Non-blocking — mode is saved locally regardless
  }
}

async function refreshStats() {
  try {
    const res = await fetch('/api/training/stats')
    if (res.ok) {
      const data = await res.json()
      stats.value = data.stats ?? stats.value
      trainingHistory.value = data.history ?? []
    }
  } catch {
    // Silently ignore — stats will show zeros
  }
}

async function exportDataset() {
  try {
    const res = await fetch('/api/training/export')
    if (!res.ok) return
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `madcop-feedback-${Date.now()}.jsonl`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch {
    // Ignore
  }
}

async function clearAll() {
  if (!confirm('确定清除所有反馈数据？此操作不可恢复。')) return
  loading.value = true
  try {
    await fetch('/api/training/clear', { method: 'POST' })
    await refreshStats()
  } finally {
    loading.value = false
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  const diff = Date.now() - d.getTime()
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return d.toLocaleDateString('zh-CN')
}

onMounted(refreshStats)
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-6 px-6 py-8">
    <!-- Title -->
    <div>
      <h2 class="text-[20px] font-semibold tracking-tight text-[var(--color-text-primary)]">
        持续学习
      </h2>
      <p class="mt-1 text-[13px] text-[var(--color-text-secondary)]">
        MadCop 是纯本地应用。所有反馈数据仅存储在你的 Mac 上，不会上传到任何服务器。
      </p>
    </div>

    <!-- Privacy banner -->
    <div class="flex items-center gap-3 rounded-xl border border-[var(--color-success)]/20 bg-[var(--color-success)]/5 px-4 py-3">
      <div class="flex-1">
        <div class="text-[12px] font-medium text-[var(--color-text-primary)]">本地优先 · 数据不离开你的设备</div>
        <div class="mt-0.5 text-[11px] text-[var(--color-text-tertiary)]">
          反馈数据存储于 <span style="font-family: ui-monospace, monospace">~/Library/MadCop/training_data/</span>
        </div>
      </div>
    </div>

    <!-- Mode selection -->
    <div class="space-y-3">
      <!-- Option: none -->
      <button
        type="button"
        :class="[
          'flex w-full items-start gap-4 rounded-xl border p-4 text-left transition-all',
          mode === 'none'
            ? 'border-[var(--color-brand)] bg-[var(--color-brand)]/5'
            : 'border-[var(--color-border)] hover:border-[var(--color-border-focus)]',
        ]"
        @click="saveMode('none')"
      >
        <div
          :class="[
            'mt-0.5 h-4 w-4 shrink-0 rounded-full border-2',
            mode === 'none' ? 'border-[var(--color-brand)] bg-[var(--color-brand)]' : 'border-[var(--color-border)]',
          ]"
        ></div>
        <div class="flex-1">
          <div class="text-[14px] font-medium text-[var(--color-text-primary)]">不学习</div>
          <div class="mt-1 text-[12px] text-[var(--color-text-tertiary)]">
            仅使用在线推理，不收集任何反馈数据。速度最快，资源消耗最低。
          </div>
        </div>
      </button>

      <!-- Option: local -->
      <button
        type="button"
        :class="[
          'flex w-full items-start gap-4 rounded-xl border p-4 text-left transition-all',
          mode === 'local'
            ? 'border-[var(--color-brand)] bg-[var(--color-brand)]/5'
            : 'border-[var(--color-border)] hover:border-[var(--color-border-focus)]',
        ]"
        @click="saveMode('local')"
      >
        <div
          :class="[
            'mt-0.5 h-4 w-4 shrink-0 rounded-full border-2',
            mode === 'local' ? 'border-[var(--color-brand)] bg-[var(--color-brand)]' : 'border-[var(--color-border)]',
          ]"
        ></div>
        <div class="flex-1">
          <div class="text-[14px] font-medium text-[var(--color-text-primary)]">本地轻量微调</div>
          <div class="mt-1 text-[12px] text-[var(--color-text-tertiary)]">
            收集你对多 LLM 答案的选择和评分，定期在本机用 LoRA 微调小模型 (Qwen3-1.5B)。
            <br/>
            数据完全保留在本地，可在下方随时查看、导出或清除。
          </div>
          <div
            class="mt-2 flex items-center gap-4 text-[10px] uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]"
            style="font-family: ui-monospace, 'SF Mono', monospace"
          >
            <span>需要 8GB+ 内存</span>
            <span>每 100 条触发</span>
            <span>~30 分钟/次</span>
          </div>
        </div>
      </button>
    </div>

    <!-- Data management -->
    <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-4">
      <div class="mb-4 flex items-center justify-between">
        <h3 class="text-[13px] font-semibold text-[var(--color-text-primary)]">数据管理</h3>
        <span
          class="text-[10px] uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]"
          style="font-family: ui-monospace, 'SF Mono', monospace"
        >
          local only
        </span>
      </div>

      <!-- Stats grid -->
      <div class="mb-4 grid grid-cols-3 gap-3">
        <div class="rounded-lg bg-[var(--color-surface)] p-3 text-center">
          <div class="text-[20px] font-semibold tabular-nums text-[var(--color-text-primary)]" style="font-family: ui-monospace, monospace">
            {{ stats.total }}
          </div>
          <div class="mt-0.5 text-[10px] text-[var(--color-text-tertiary)]">已收集反馈</div>
        </div>
        <div class="rounded-lg bg-[var(--color-surface)] p-3 text-center">
          <div class="text-[20px] font-semibold tabular-nums text-[var(--color-text-primary)]" style="font-family: ui-monospace, monospace">
            {{ stats.used }}
          </div>
          <div class="mt-0.5 text-[10px] text-[var(--color-text-tertiary)]">已用于训练</div>
        </div>
        <div class="rounded-lg bg-[var(--color-surface)] p-3 text-center">
          <div class="text-[13px] font-medium text-[var(--color-text-primary)]">
            {{ formatDate(stats.lastTrain) }}
          </div>
          <div class="mt-0.5 text-[10px] text-[var(--color-text-tertiary)]">上次微调</div>
        </div>
      </div>

      <!-- Actions -->
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-[12px] font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-container)]"
          @click="exportDataset"
        >
          导出训练集
        </button>
        <button
          type="button"
          :disabled="loading || stats.total === 0"
          :class="[
            'rounded-lg border px-3 py-1.5 text-[12px] font-medium transition-colors',
            loading || stats.total === 0
              ? 'cursor-not-allowed border-[var(--color-border)] text-[var(--color-text-tertiary)]'
              : 'border-[var(--color-error)]/30 text-[var(--color-error)] hover:bg-[var(--color-error)]/5',
          ]"
          @click="clearAll"
        >
          清除所有数据
        </button>
      </div>
    </div>

    <!-- Training history -->
    <div v-if="trainingHistory.length > 0" class="space-y-2">
      <h3 class="text-[13px] font-semibold text-[var(--color-text-primary)]">微调历史</h3>
      <div
        v-for="record in trainingHistory"
        :key="record.id"
        class="flex items-center justify-between rounded-lg border border-[var(--color-border)] px-4 py-2.5"
      >
        <div class="flex items-center gap-3">
          <span
            class="inline-block h-2 w-2 rounded-full"
            :class="record.status === 'completed' ? 'bg-[var(--color-success)]' : 'bg-[var(--color-error)]'"
          ></span>
          <span class="text-[12px] text-[var(--color-text-primary)]">{{ formatDate(record.date) }}</span>
        </div>
        <div
          class="flex items-center gap-4 text-[10px] tabular-nums text-[var(--color-text-tertiary)]"
          style="font-family: ui-monospace, 'SF Mono', monospace"
        >
          <span>{{ record.samples }} samples</span>
          <span>{{ record.duration }}</span>
          <span>loss {{ record.loss.toFixed(3) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
