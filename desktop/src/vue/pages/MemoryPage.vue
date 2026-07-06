<script setup lang="ts">
/**
 * MemoryPage — 用户能看到 "MadCop 记住了我什么" + "可以编辑/删除"
 *
 * 这是用户对"持续学习"的可视化界面：
 * 1. 偏好（用户对回答的反馈自动提炼出来的习惯）
 * 2. 重要事实（用户在对话中说"我习惯用 X 框架"等）
 * 3. 训练状态（如果用户开启了 LoRA，显示训练了多少次、用了多少样本）
 *
 * 设计原则:
 *  - 默认 LoRA 是关闭的（保护用户资源）
 *  - 数据完全本地，无云端
 *  - 用户可以增/删/改任何条目
 */

import { ref, computed, onMounted } from 'vue'

// ─── State ─────────────────────────────────────────────────────────────

interface MemoryEntry {
  id: string
  category: 'preference' | 'fact' | 'style'
  content: string
  source: 'auto' | 'manual'  // auto = LLM 提取的, manual = 用户手填
  confidence: number  // 0-1, 自动提取的置信度
  createdAt: string
  usedCount: number  // 被引用过多少次
}

interface TrainingRecord {
  id: string
  date: string
  samples: number
  duration: string
  loss: number
  status: 'completed' | 'failed'
  baseModel: string  // 'Qwen3-1.5B' 等
}

const learningEnabled = ref(false)
const loraBaseModel = ref('Qwen3-1.5B')
const memoryEntries = ref<MemoryEntry[]>([])
const trainingHistory = ref<TrainingRecord[]>([])
const loading = ref(false)
const newEntry = ref('')

// ─── Resource estimation ───────────────────────────────────────────────

const resourceEstimate = computed(() => {
  // 估算训练这个用户的数据需要多少资源
  const samples = memoryEntries.value.length
  if (samples === 0) {
    return { time: '—', memory: '—', disk: '—' }
  }
  // 经验值: 1.5B 模型 + 100 samples ≈ 25 分钟, 6GB 内存, 30MB 磁盘
  const minutes = Math.round((samples / 100) * 25)
  const memoryGB = 6
  const diskMB = Math.round((samples / 100) * 30)
  return {
    time: minutes < 60 ? `~${minutes} 分钟` : `~${(minutes / 60).toFixed(1)} 小时`,
    memory: `${memoryGB} GB 内存`,
    disk: diskMB < 1024 ? `~${diskMB} MB` : `~${(diskMB / 1024).toFixed(1)} GB`,
  }
})

// ─── Sample data (replace with API) ────────────────────────────────────

const SAMPLE_ENTRIES: MemoryEntry[] = [
  {
    id: 'm1',
    category: 'preference',
    content: '回答时不要使用 emoji',
    source: 'auto',
    confidence: 0.92,
    createdAt: new Date(Date.now() - 86400000 * 3).toISOString(),
    usedCount: 47,
  },
  {
    id: 'm2',
    category: 'preference',
    content: '代码示例优先用 TypeScript 而非 JavaScript',
    source: 'auto',
    confidence: 0.87,
    createdAt: new Date(Date.now() - 86400000 * 5).toISOString(),
    usedCount: 23,
  },
  {
    id: 'm3',
    category: 'style',
    content: '回复要简洁，避免冗长解释',
    source: 'auto',
    confidence: 0.78,
    createdAt: new Date(Date.now() - 86400000 * 2).toISOString(),
    usedCount: 31,
  },
  {
    id: 'm4',
    category: 'fact',
    content: '我常用 FastAPI + SQLAlchemy 做后端',
    source: 'manual',
    confidence: 1.0,
    createdAt: new Date(Date.now() - 86400000 * 7).toISOString(),
    usedCount: 12,
  },
  {
    id: 'm5',
    category: 'preference',
    content: '命名风格用驼峰，不用下划线',
    source: 'auto',
    confidence: 0.81,
    createdAt: new Date(Date.now() - 86400000 * 1).toISOString(),
    usedCount: 8,
  },
]

const SAMPLE_TRAINING: TrainingRecord[] = [
  {
    id: 't1',
    date: new Date(Date.now() - 86400000 * 2).toISOString(),
    samples: 120,
    duration: '28 分钟',
    loss: 1.42,
    status: 'completed',
    baseModel: 'Qwen3-1.5B',
  },
]

// ─── Actions ───────────────────────────────────────────────────────────

async function loadAll() {
  loading.value = true
  try {
    // 实际项目里: const r = await fetch('/api/memory/entries') ...
    memoryEntries.value = SAMPLE_ENTRIES
    trainingHistory.value = SAMPLE_TRAINING
    learningEnabled.value = false
  } finally {
    loading.value = false
  }
}

async function toggleLearning(enabled: boolean) {
  learningEnabled.value = enabled
  try {
    await fetch('/api/training/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: enabled ? 'local' : 'none' }),
    })
  } catch {
    // ignore
  }
}

async function deleteEntry(id: string) {
  memoryEntries.value = memoryEntries.value.filter((e) => e.id !== id)
  // await fetch(`/api/memory/entries/${id}`, { method: 'DELETE' })
}

async function addEntry() {
  const content = newEntry.value.trim()
  if (!content) return
  memoryEntries.value.unshift({
    id: `m${Date.now()}`,
    category: 'fact',
    content,
    source: 'manual',
    confidence: 1.0,
    createdAt: new Date().toISOString(),
    usedCount: 0,
  })
  newEntry.value = ''
  // await fetch('/api/memory/entries', { method: 'POST', body: JSON.stringify(...) })
}

async function triggerTraining() {
  if (memoryEntries.value.length < 10) {
    alert('至少需要 10 条记忆才能训练')
    return
  }
  // await fetch('/api/training/trigger', { method: 'POST' })
  alert('已提交训练任务。完成后会在下方历史中显示。')
}

function formatRelative(iso: string): string {
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return `${Math.floor(diff / 86_400_000)} 天前`
}

const categoryLabel = {
  preference: '偏好',
  fact: '事实',
  style: '风格',
}

const categoryColor = {
  preference: 'bg-[var(--color-brand)]/10 text-[var(--color-brand)]',
  fact: 'bg-[var(--color-success)]/10 text-[var(--color-success)]',
  style: 'bg-[var(--color-warning)]/10 text-[var(--color-warning)]',
}

onMounted(loadAll)
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-8 px-6 py-8">
    <!-- Title + toggle -->
    <header class="flex items-start justify-between">
      <div>
        <h2 class="text-[20px] font-semibold tracking-tight text-[var(--color-text-primary)]">记忆</h2>
        <p class="mt-1 text-[13px] text-[var(--color-text-secondary)]">
          MadCop 记住的关于你的信息。你可以查看、编辑、删除。
        </p>
      </div>
      <!-- Big toggle -->
      <button
        type="button"
        role="switch"
        :aria-checked="learningEnabled"
        :class="[
          'relative h-7 w-12 shrink-0 rounded-full transition-colors',
          learningEnabled ? 'bg-[var(--color-brand)]' : 'bg-[var(--color-border)]',
        ]"
        @click="toggleLearning(!learningEnabled)"
      >
        <span
          :class="[
            'absolute top-0.5 h-6 w-6 rounded-full bg-white shadow-sm transition-transform',
            learningEnabled ? 'translate-x-5' : 'translate-x-0.5',
          ]"
        ></span>
      </button>
    </header>

    <!-- Toggle description -->
    <p
      v-if="learningEnabled"
      class="rounded-lg border border-[var(--color-brand)]/30 bg-[var(--color-brand)]/5 px-3 py-2 text-[12px] text-[var(--color-text-primary)]"
    >
      持续学习已开启。MadCop 会从你的反馈中提炼偏好，达到一定数据量后会自动微调。
    </p>
    <p
      v-else
      class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-3 py-2 text-[12px] text-[var(--color-text-tertiary)]"
    >
      持续学习默认关闭。开启后，MadCop 会从你的反馈中学习——所有数据保留在本地。
    </p>

    <!-- Resource estimate (shown only when toggled on) -->
    <div
      v-if="learningEnabled"
      class="rounded-xl border border-[var(--color-border)] p-4"
    >
      <div class="mb-2 text-[12px] font-semibold text-[var(--color-text-primary)]">资源消耗预估</div>
      <div
        class="grid grid-cols-3 gap-3 text-[11px]"
        style="font-family: ui-monospace, 'SF Mono', monospace"
      >
        <div class="rounded-lg bg-[var(--color-surface-container)] p-2 text-center">
          <div class="text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)]">训练时间</div>
          <div class="mt-1 text-[14px] font-medium text-[var(--color-text-primary)]">{{ resourceEstimate.time }}</div>
        </div>
        <div class="rounded-lg bg-[var(--color-surface-container)] p-2 text-center">
          <div class="text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)]">占用内存</div>
          <div class="mt-1 text-[14px] font-medium text-[var(--color-text-primary)]">{{ resourceEstimate.memory }}</div>
        </div>
        <div class="rounded-lg bg-[var(--color-surface-container)] p-2 text-center">
          <div class="text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)]">磁盘空间</div>
          <div class="mt-1 text-[14px] font-medium text-[var(--color-text-primary)]">{{ resourceEstimate.disk }}</div>
        </div>
      </div>
    </div>

    <!-- Add manual entry -->
    <div class="rounded-xl border border-[var(--color-border)] p-4">
      <div class="mb-2 text-[12px] font-semibold text-[var(--color-text-primary)]">添加一条手动记忆</div>
      <div class="flex gap-2">
        <input
          v-model="newEntry"
          type="text"
          placeholder="例如：我常用 FastAPI 做后端"
          class="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-[13px] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:border-[var(--color-brand)] focus:outline-none"
          @keydown.enter="addEntry"
        />
        <button
          type="button"
          class="rounded-lg bg-[var(--color-brand)] px-4 py-2 text-[12px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          :disabled="!newEntry.trim()"
          @click="addEntry"
        >
          添加
        </button>
      </div>
    </div>

    <!-- Memory list -->
    <section>
      <div class="mb-3 flex items-center justify-between">
        <h3 class="text-[13px] font-semibold text-[var(--color-text-primary)]">
          已记住 ({{ memoryEntries.length }})
        </h3>
        <div class="flex items-center gap-1 text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)]"
             style="font-family: ui-monospace, 'SF Mono', monospace">
          <span class="rounded bg-[var(--color-brand)]/10 px-1.5 py-0.5 text-[var(--color-brand)]">偏好</span>
          <span class="rounded bg-[var(--color-success)]/10 px-1.5 py-0.5 text-[var(--color-success)]">事实</span>
          <span class="rounded bg-[var(--color-warning)]/10 px-1.5 py-0.5 text-[var(--color-warning)]">风格</span>
        </div>
      </div>
      <div class="space-y-2">
        <div
          v-for="entry in memoryEntries"
          :key="entry.id"
          class="group flex items-start gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 transition-colors hover:border-[var(--color-border-focus)]"
        >
          <!-- Category badge -->
          <span
            :class="['shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider', categoryColor[entry.category]]"
            style="font-family: ui-monospace, 'SF Mono', monospace"
          >
            {{ categoryLabel[entry.category] }}
          </span>
          <!-- Content -->
          <div class="flex-1 min-w-0">
            <p class="text-[13px] text-[var(--color-text-primary)]">{{ entry.content }}</p>
            <div
              class="mt-1 flex items-center gap-3 text-[10px] text-[var(--color-text-tertiary)]"
              style="font-family: ui-monospace, 'SF Mono', monospace"
            >
              <span v-if="entry.source === 'auto'">置信度 {{ Math.round(entry.confidence * 100) }}%</span>
              <span v-else>手动</span>
              <span>·</span>
              <span>{{ formatRelative(entry.createdAt) }}</span>
              <span v-if="entry.usedCount > 0">· 已用 {{ entry.usedCount }} 次</span>
            </div>
          </div>
          <!-- Delete -->
          <button
            type="button"
            class="shrink-0 rounded p-1 text-[var(--color-text-tertiary)] opacity-0 transition-opacity hover:bg-[var(--color-error)]/10 hover:text-[var(--color-error)] group-hover:opacity-100"
            :aria-label="`删除 ${entry.content}`"
            @click="deleteEntry(entry.id)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div
          v-if="memoryEntries.length === 0 && !loading"
          class="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-[12px] text-[var(--color-text-tertiary)]"
        >
          还没有记忆。用一段时间 MadCop 后，会自动从这里开始积累。
        </div>
      </div>
    </section>

    <!-- Training history -->
    <section v-if="learningEnabled && trainingHistory.length > 0">
      <h3 class="mb-3 text-[13px] font-semibold text-[var(--color-text-primary)]">微调历史</h3>
      <div class="space-y-1.5">
        <div
          v-for="r in trainingHistory"
          :key="r.id"
          class="flex items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2"
        >
          <span
            class="inline-block h-2 w-2 rounded-full"
            :class="r.status === 'completed' ? 'bg-[var(--color-success)]' : 'bg-[var(--color-error)]'"
          ></span>
          <span class="flex-1 text-[12px] text-[var(--color-text-primary)]">{{ formatRelative(r.date) }}</span>
          <span
            class="text-[10px] tabular-nums text-[var(--color-text-tertiary)]"
            style="font-family: ui-monospace, 'SF Mono', monospace"
          >
            {{ r.samples }} 样本 · {{ r.duration }} · {{ r.baseModel }} · loss {{ r.loss.toFixed(2) }}
          </span>
        </div>
      </div>
    </section>

    <!-- Trigger button (shown only when learning on and enough data) -->
    <div v-if="learningEnabled" class="rounded-xl border border-[var(--color-border)] p-4">
      <div class="flex items-center justify-between">
        <div>
          <div class="text-[12px] font-medium text-[var(--color-text-primary)]">手动触发微调</div>
          <div class="mt-0.5 text-[11px] text-[var(--color-text-tertiary)]">
            通常每积累 100 条新记忆会自动触发。也可手动。
          </div>
        </div>
        <button
          type="button"
          :disabled="memoryEntries.length < 10"
          class="rounded-lg bg-[var(--color-brand)] px-4 py-2 text-[12px] font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          @click="triggerTraining"
        >
          开始微调
        </button>
      </div>
    </div>
  </div>
</template>
