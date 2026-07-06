<script setup lang="ts">
/**
 * ArenaPage — multi-LLM comparison.
 *
 * Send the same prompt to N models in parallel, show all results side-by-side.
 * This is the practical "LoRA across models" effect:
 * - Shared memory-enriched system prompt = consistent user style
 * - Multiple model outputs = genuine diversity in thinking
 *
 * Each model's output includes a "score" column for the user to rate.
 * The user's chosen model is recorded for continuous learning.
 */

import { ref, computed, onMounted } from 'vue'

interface AvailableModel {
  model: string
  provider_id: string
  label: string
  active: boolean
}

interface ArenaResult {
  model: string
  provider: string
  text: string
  elapsed_sec: number
  ok: boolean
  error?: string
  // User's rating
  score?: number  // 0-5
  chosen?: boolean
}

// ─── State ─────────────────────────────────────────────────────────────

const userInput = ref('')
const availableModels = ref<AvailableModel[]>([])
const selectedModels = ref<string[]>([])
const isRunning = ref(false)
const results = ref<ArenaResult[]>([])
const memoryInjected = ref(false)
const sysPromptSize = ref(0)

// ─── Load available models on mount ────────────────────────────────────

async function loadModels() {
  try {
    const res = await fetch('/api/arena/available-models')
    if (res.ok) {
      const data = await res.json()
      availableModels.value = data.models || []
      // Auto-select all by default
      selectedModels.value = availableModels.value.map((m) => m.model)
    }
  } catch {
    // ignore
  }
}

onMounted(loadModels)

// ─── Run arena ─────────────────────────────────────────────────────────

async function runArena() {
  if (!userInput.value.trim() || isRunning.value) return
  if (selectedModels.value.length === 0) {
    alert('请至少选择一个模型')
    return
  }
  isRunning.value = true
  results.value = []
  try {
    const res = await fetch('/api/arena/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_message: userInput.value,
        models: selectedModels.value,
        temperature: 0.7,
        max_tokens: 1024,
      }),
    })
    if (res.ok) {
      const data = await res.json()
      results.value = (data.results || []).map((r: ArenaResult) => ({
        ...r,
        score: 0,
        chosen: false,
      }))
      memoryInjected.value = data.memory_injected
      sysPromptSize.value = data.sys_prompt_size
    }
  } catch (e) {
    console.error('Arena failed', e)
  } finally {
    isRunning.value = false
  }
}

// ─── Rating + feedback ────────────────────────────────────────────────

async function rateResult(idx: number, score: number) {
  const r = results.value[idx]
  r.score = score
  // Send to training feedback
  try {
    await fetch('/api/training/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_type: 'arena',
        user_request: userInput.value,
        agent_outputs: Object.fromEntries(
          results.value.map((x) => [x.model, x.text || ''])
        ),
        user_choice: r.model,
        user_score: score,
      }),
    })
  } catch {
    // ignore
  }
}

function chooseResult(idx: number) {
  for (let i = 0; i < results.value.length; i++) {
    results.value[i].chosen = i === idx
  }
}

function toggleModel(modelName: string) {
  const idx = selectedModels.value.indexOf(modelName)
  if (idx >= 0) {
    selectedModels.value.splice(idx, 1)
  } else {
    selectedModels.value.push(modelName)
  }
}

function copyText(text: string) {
  navigator.clipboard?.writeText(text)
}
</script>

<template>
  <div class="flex h-full flex-col bg-[var(--color-surface)]">
    <!-- Header -->
    <header class="border-b border-[var(--color-border)] px-6 py-4">
      <h1 class="text-[18px] font-semibold tracking-tight text-[var(--color-text-primary)]">Arena</h1>
      <p class="mt-0.5 text-[11px] text-[var(--color-text-tertiary)]">
        同一个问题问多个模型，对比结果。所有模型共享你的记忆库，所以口吻一致——差异在内容上。
      </p>
    </header>

    <!-- Input area -->
    <div class="border-b border-[var(--color-border-separator)] px-6 py-4">
      <textarea
        v-model="userInput"
        rows="3"
        placeholder="输入问题，所有选中的模型会同时回答..."
        class="w-full resize-none rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-[13px] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:border-[var(--color-brand)] focus:outline-none"
      />
      <!-- Model chips -->
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <span class="text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)]"
              style="font-family: ui-monospace, 'SF Mono', monospace">models</span>
        <button
          v-for="m in availableModels"
          :key="m.model"
          type="button"
          :class="[
            'rounded-full border px-3 py-1 text-[11px] transition-colors',
            selectedModels.includes(m.model)
              ? 'border-[var(--color-brand)] bg-[var(--color-brand)]/10 text-[var(--color-brand)]'
              : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-border-focus)]',
          ]"
          @click="toggleModel(m.model)"
        >
          {{ m.label }}
        </button>
        <button
          type="button"
          :disabled="isRunning || !userInput.trim() || selectedModels.length === 0"
          :class="[
            'ml-auto rounded-lg px-4 py-1.5 text-[12px] font-medium transition-opacity',
            isRunning || !userInput.trim() || selectedModels.length === 0
              ? 'cursor-not-allowed bg-[var(--color-surface-container)] text-[var(--color-text-tertiary)]'
              : 'bg-[var(--color-brand)] text-white hover:opacity-90',
          ]"
          @click="runArena"
        >
          {{ isRunning ? '运行中…' : '运行' }}
        </button>
      </div>
    </div>

    <!-- Memory indicator -->
    <div
      v-if="results.length > 0 && memoryInjected"
      class="border-b border-[var(--color-border-separator)] bg-[var(--color-surface-container-low)] px-6 py-2"
    >
      <div class="flex items-center gap-2 text-[10px] text-[var(--color-text-tertiary)]"
           style="font-family: ui-monospace, 'SF Mono', monospace">
        <span class="rounded bg-[var(--color-success)]/10 px-1.5 py-0.5 text-[var(--color-success)]">memory injected</span>
        <span>系统提示词 {{ sysPromptSize }} 字符 · 所有模型共享同一份</span>
      </div>
    </div>

    <!-- Results -->
    <div class="flex-1 overflow-y-auto p-6">
      <div v-if="results.length === 0" class="flex h-full flex-col items-center justify-center">
        <div class="text-[12px] text-[var(--color-text-tertiary)]">输入问题并选择模型，点击"运行"</div>
        <div class="mt-1 text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)] opacity-50"
             style="font-family: ui-monospace, 'SF Mono', monospace">multi-llm · parallel</div>
      </div>

      <div v-else class="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div
          v-for="(r, idx) in results"
          :key="r.model"
          :class="[
            'flex flex-col overflow-hidden rounded-xl border bg-[var(--color-surface-container-lowest)]',
            r.chosen
              ? 'border-[var(--color-brand)] ring-2 ring-[var(--color-brand)]/20'
              : 'border-[var(--color-border)]',
          ]"
        >
          <!-- Card header -->
          <div class="flex items-center justify-between border-b border-[var(--color-border-separator)] px-4 py-2.5">
            <div class="flex items-center gap-2">
              <span class="text-[12px] font-medium text-[var(--color-text-primary)]">{{ r.provider }}</span>
              <span
                v-if="r.ok"
                class="rounded bg-[var(--color-surface-container)] px-1.5 py-0.5 text-[10px] tabular-nums text-[var(--color-text-tertiary)]"
                style="font-family: ui-monospace, 'SF Mono', monospace"
              >
                {{ r.elapsed_sec }}s
              </span>
            </div>
            <button
              v-if="r.text"
              type="button"
              class="text-[10px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]"
              @click="copyText(r.text)"
            >
              复制
            </button>
          </div>

          <!-- Body -->
          <div class="flex-1 overflow-y-auto p-4">
            <div v-if="r.ok" class="whitespace-pre-wrap text-[13px] leading-relaxed text-[var(--color-text-primary)]">
              {{ r.text }}
            </div>
            <div v-else class="text-[12px] text-[var(--color-error)]">
              <div class="font-semibold">错误</div>
              <div class="mt-1">{{ r.error }}</div>
            </div>
          </div>

          <!-- Footer: rating -->
          <div v-if="r.ok" class="flex items-center gap-3 border-t border-[var(--color-border-separator)] px-4 py-2.5">
            <span class="text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)]"
                  style="font-family: ui-monospace, 'SF Mono', monospace">rate</span>
            <button
              v-for="n in 5"
              :key="n"
              type="button"
              :class="[
                'text-base transition-transform hover:scale-110',
                n <= (r.score || 0) ? 'text-yellow-500' : 'text-[var(--color-text-tertiary)]',
              ]"
              @click="rateResult(idx, n)"
            >★</button>
            <button
              type="button"
              :class="[
                'ml-auto rounded-md px-2 py-0.5 text-[10px] font-medium transition-colors',
                r.chosen
                  ? 'bg-[var(--color-brand)] text-white'
                  : 'border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-brand)]',
              ]"
              @click="chooseResult(idx)"
            >
              {{ r.chosen ? '✓ 已选' : '选为最佳' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
