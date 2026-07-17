<script setup lang="ts">
/**
 * MemoryPage — user-facing view of ALL memory layers.
 *
 * Maps to the 4 backend sections in `_build_memory_system_prompt`:
 *   1. 用户画像   (profile facts, tagged 'user-profile')
 *   2. 相关记忆   (relevant: episodic + semantic + scenario + insight search)
 *   3. 用户偏好   (preferences: ReflectiveMemory)
 *   4. 可用技能   (skills: auto-distilled)
 *
 * The other memory layers (Scenario, Insight, Episodic) are
 * automatically indexed & retrieved under "相关记忆" — users see
 * them as one bucket.
 */

import { ref, computed, onMounted } from 'vue'
import { getApiUrl } from '../api/client'

// ─── Data model ────────────────────────────────────────────────────────

type MemoryLayer = 'profile' | 'relevant' | 'preferences' | 'skills'

interface ProfileFact {
  id: string
  content: string
  source: 'auto' | 'manual'
  confidence: number
  createdAt: string
  usedCount: number
}

interface RelevantMemory {
  id: string
  content: string
  layer: 'episodic' | 'semantic' | 'scenario' | 'insight'
  relevance: number
  createdAt: string
  preview: string  // first 80 chars
}

interface Preference {
  id: string
  text: string
  kind: 'likes' | 'dislikes'
  strength: number  // 0-1
  createdAt: string
}

interface Skill {
  id: string
  name: string
  description: string
  source: 'auto-distilled' | 'user-created'
  triggered: number
}

// ─── State ─────────────────────────────────────────────────────────────

const learningEnabled = ref(false)
const loraBaseModel = ref('Qwen3-1.5B')
const profile = ref<ProfileFact[]>([])
const relevant = ref<RelevantMemory[]>([])
const preferences = ref<Preference[]>([])
const skills = ref<Skill[]>([])
const loading = ref(false)
const activeTab = ref<MemoryLayer>('profile')
const newProfileFact = ref('')

// ─── Sample data ──────────────────────────────────────────────────────
// NOTE: all sample data removed for privacy + correctness. Previously
// this page shipped real PII (name, phone, employer) hardcoded as
// "sample" data and never called the backend. Now loadAll() fetches
// from the real memory endpoints and shows an empty state when there
// is no data yet.

const SAMPLE_PROFILE: ProfileFact[] = []
const SAMPLE_RELEVANT: RelevantMemory[] = []
const SAMPLE_PREFERENCES: Preference[] = []
const SAMPLE_SKILLS: Skill[] = []

// ─── Computed counts ──────────────────────────────────────────────────

const totalCount = computed(
  () => profile.value.length + relevant.value.length + preferences.value.length + skills.value.length,
)

const resourceEstimate = computed(() => {
  const samples = totalCount.value
  if (samples === 0) return { time: '—', memory: '—', disk: '—' }
  const minutes = Math.round((samples / 100) * 25)
  return {
    time: minutes < 60 ? `~${minutes} 分钟` : `~${(minutes / 60).toFixed(1)} 小时`,
    memory: '6 GB 内存',
    disk: samples < 2000 ? '~30 MB' : '~120 MB',
  }
})

// ─── Layer meta ───────────────────────────────────────────────────────

const LAYERS: { key: MemoryLayer; label: string; desc: string; count: () => number }[] = [
  { key: 'profile', label: '画像', desc: '关于你的基本信息', count: () => profile.value.length },
  { key: 'relevant', label: '相关记忆', desc: '对话中用过的上下文', count: () => relevant.value.length },
  { key: 'preferences', label: '偏好', desc: '你喜欢 / 不喜欢什么', count: () => preferences.value.length },
  { key: 'skills', label: '技能', desc: '提炼的可复用流程', count: () => skills.value.length },
]

// ─── Actions ──────────────────────────────────────────────────────────

async function loadAll() {
  loading.value = true
  try {
    // Fetch real memory data from the backend. Each endpoint returns
    // its layer's facts; if the backend is unreachable or returns
    // nothing, we fall back to empty arrays (not fake data).
    const [profRes, relRes, prefRes, sklRes] = await Promise.allSettled([
      fetch(getApiUrl('/api/memory/profile')),
      fetch(getApiUrl('/api/memory/relevant')),
      fetch(getApiUrl('/api/memory/preferences')),
      fetch(getApiUrl('/api/skills')),
    ])
    if (profRes.status === 'fulfilled' && profRes.value.ok) {
      const d = await profRes.value.json()
      profile.value = (d.facts || d.profile || d.data || []).map((f: any) => ({
        id: f.id || f.key || Math.random().toString(36),
        content: f.content || f.value || f.fact || '',
        source: f.source || 'auto',
        confidence: f.confidence ?? 1.0,
        createdAt: f.createdAt || f.created_at || new Date().toISOString(),
        usedCount: f.usedCount || f.used_count || 0,
      }))
    }
    if (relRes.status === 'fulfilled' && relRes.value.ok) {
      const d = await relRes.value.json()
      relevant.value = (d.memories || d.relevant || d.data || []).map((m: any) => ({
        id: m.id || Math.random().toString(36),
        content: m.content || m.text || '',
        layer: m.layer || 'episodic',
        relevance: m.relevance ?? m.score ?? 0.5,
        createdAt: m.createdAt || m.created_at || new Date().toISOString(),
        preview: (m.content || m.text || '').slice(0, 60),
      }))
    }
    if (prefRes.status === 'fulfilled' && prefRes.value.ok) {
      const d = await prefRes.value.json()
      preferences.value = (d.preferences || d.data || []).map((p: any) => ({
        id: p.id || Math.random().toString(36),
        text: p.text || p.content || '',
        kind: p.kind || 'likes',
        strength: p.strength ?? 0.5,
        createdAt: p.createdAt || p.created_at || new Date().toISOString(),
      }))
    }
    if (sklRes.status === 'fulfilled' && sklRes.value.ok) {
      const d = await sklRes.value.json()
      skills.value = (d.skills || d.data || []).map((s: any) => ({
        id: s.id || s.name || Math.random().toString(36),
        name: s.name || s.title || '',
        description: s.description || s.summary || '',
        source: s.source || 'auto-distilled',
        triggered: s.triggered || s.use_count || 0,
      }))
    }
  } catch {
    // Network error — leave arrays empty (empty state shows).
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
  } catch {}
}

async function deleteItem(layer: MemoryLayer, id: string) {
  if (layer === 'profile') profile.value = profile.value.filter((x) => x.id !== id)
  if (layer === 'relevant') relevant.value = relevant.value.filter((x) => x.id !== id)
  if (layer === 'preferences') preferences.value = preferences.value.filter((x) => x.id !== id)
  if (layer === 'skills') skills.value = skills.value.filter((x) => x.id !== id)
  // await fetch(`/api/memory/${layer}/${id}`, { method: 'DELETE' })
}

async function addProfileFact() {
  const content = newProfileFact.value.trim()
  if (!content) return
  profile.value.unshift({
    id: `p${Date.now()}`,
    content,
    source: 'manual',
    confidence: 1.0,
    createdAt: new Date().toISOString(),
    usedCount: 0,
  })
  newProfileFact.value = ''
}

function formatRelative(iso: string): string {
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 86_400_000 * 30) return `${Math.floor(diff / 86_400_000)} 天前`
  return d.toLocaleDateString('zh-CN')
}

const LAYER_COLOR: Record<string, string> = {
  episodic: 'text-[var(--color-text-tertiary)]',
  semantic: 'text-[var(--color-text-primary)]',
  scenario: 'text-[var(--color-text-tertiary)]',
  insight: 'text-[var(--color-brand)]',
}

const LAYER_LABEL: Record<string, string> = {
  episodic: '事件',
  semantic: '事实',
  scenario: '场景',
  insight: '洞察',
}

onMounted(loadAll)
</script>

<template>
  <div class="mx-auto max-w-4xl space-y-5">
    <!-- Header card -->
    <header class="flex items-start justify-between gap-4 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-5 py-5">
      <div class="min-w-0">
        <div class="mb-2 text-[11px] font-semibold tracking-wide text-[var(--color-text-tertiary)]">AI</div>
        <div class="mb-2 flex items-center gap-2">
          <span class="material-symbols-outlined text-[20px] text-[var(--color-brand)]" style="fontVariationSettings: 'FILL' 1">psychology</span>
          <h2 class="text-lg font-semibold tracking-tight text-[var(--color-text-primary)]">记忆</h2>
          <span class="rounded-full bg-[var(--color-surface)] px-2 py-0.5 text-[11px] font-semibold tabular-nums text-[var(--color-text-tertiary)] border border-[var(--color-border)]">
            {{ totalCount }}
          </span>
        </div>
        <p class="text-sm leading-6 text-[var(--color-text-secondary)]">
          MadCop 记住的关于你的所有信息。共 {{ totalCount }} 条。
        </p>
      </div>
      <div class="flex shrink-0 flex-col items-end gap-1.5">
        <span class="text-[10px] font-medium text-[var(--color-text-tertiary)]">持续学习</span>
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
      </div>
    </header>

    <!-- Toggle hint -->
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
      持续学习默认关闭。开启后 MadCop 会从你的反馈中学习——所有数据保留在本地。
    </p>

    <!-- Resource estimate (when on) -->
    <div
      v-if="learningEnabled"
      class="rounded-xl border border-[var(--color-border)] p-4"
    >
      <div class="mb-2 text-[12px] font-semibold text-[var(--color-text-primary)]">资源消耗预估</div>
      <div
        class="grid grid-cols-3 gap-3 text-[11px]"
        style="font-family: var(--font-mono)"
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

    <!-- Tab switcher -->
    <div class="flex items-center gap-1 border-b border-[var(--color-border-separator)]">
      <button
        v-for="l in LAYERS"
        :key="l.key"
        type="button"
        :class="[
          'flex items-center gap-1.5 border-b-2 px-3 py-2 text-[12px] font-medium transition-colors',
          activeTab === l.key
            ? 'border-[var(--color-brand)] text-[var(--color-text-primary)]'
            : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
        ]"
        @click="activeTab = l.key"
      >
        {{ l.label }}
        <span
          class="rounded bg-[var(--color-surface-container)] px-1.5 py-0.5 text-[10px] tabular-nums"
          style="font-family: var(--font-mono)"
        >
          {{ l.count() }}
        </span>
      </button>
    </div>

    <!-- Tab descriptions -->
    <p class="text-[11px] text-[var(--color-text-tertiary)]">
      {{ LAYERS.find(l => l.key === activeTab)?.desc }}
    </p>

    <!-- Add profile fact (only on profile tab) -->
    <div v-if="activeTab === 'profile'" class="rounded-xl border border-[var(--color-border)] p-4">
      <div class="mb-2 text-[12px] font-semibold text-[var(--color-text-primary)]">添加一条事实</div>
      <div class="flex gap-2">
        <input
          v-model="newProfileFact"
          type="text"
          placeholder="例如：我常用 FastAPI 做后端"
          class="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-[13px] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:border-[var(--color-brand)] focus:outline-none"
          @keydown.enter="addProfileFact"
        />
        <button
          type="button"
          class="rounded-lg bg-[var(--color-brand)] px-4 py-2 text-[12px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          :disabled="!newProfileFact.trim()"
          @click="addProfileFact"
        >添加</button>
      </div>
    </div>

    <!-- Profile list -->
    <section v-if="activeTab === 'profile'" class="space-y-2">
      <div
        v-for="p in profile"
        :key="p.id"
        class="group flex items-start gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 transition-colors hover:border-[var(--color-border-focus)]"
      >
        <span
          v-if="p.source === 'manual'"
          class="shrink-0 rounded bg-[var(--color-success)]/10 px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-success)]"
          style="font-family: var(--font-mono)"
        >手动</span>
        <span
          v-else
          class="shrink-0 rounded bg-[var(--color-surface-container)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-text-tertiary)]"
          style="font-family: var(--font-mono)"
        >{{ Math.round(p.confidence * 100) }}%</span>
        <div class="flex-1 min-w-0">
          <p class="text-[13px] text-[var(--color-text-primary)]">{{ p.content }}</p>
          <div
            class="mt-1 flex items-center gap-3 text-[10px] text-[var(--color-text-tertiary)]"
            style="font-family: var(--font-mono)"
          >
            <span>{{ formatRelative(p.createdAt) }}</span>
            <span v-if="p.usedCount > 0">· 已用 {{ p.usedCount }} 次</span>
          </div>
        </div>
        <button
          type="button"
          class="shrink-0 rounded p-1 text-[var(--color-text-tertiary)] opacity-0 transition-opacity hover:bg-[var(--color-error)]/10 hover:text-[var(--color-error)] group-hover:opacity-100"
          :aria-label="`删除 ${p.content}`"
          @click="deleteItem('profile', p.id)"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
    </section>

    <!-- Relevant memories (grouped by layer) -->
    <section v-if="activeTab === 'relevant'" class="space-y-3">
      <div
        v-for="layer in ['episodic', 'semantic', 'scenario', 'insight']"
        :key="layer"
      >
        <div
          class="mb-1.5 flex items-center gap-2 text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)]"
          style="font-family: var(--font-mono)"
        >
          <span>{{ LAYER_LABEL[layer] }}</span>
          <span class="h-px flex-1 bg-[var(--color-border-separator)]"></span>
          <span class="tabular-nums">{{ relevant.filter(r => r.layer === layer).length }}</span>
        </div>
        <div class="space-y-1.5">
          <div
            v-for="r in relevant.filter(x => x.layer === layer)"
            :key="r.id"
            class="group flex items-start gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
          >
            <span
              class="shrink-0 rounded px-1.5 py-0.5 text-[10px] tabular-nums"
              :class="layer === 'insight' ? 'bg-[var(--color-brand)]/10 text-[var(--color-brand)]' : 'bg-[var(--color-surface-container)] text-[var(--color-text-tertiary)]'"
              style="font-family: var(--font-mono)"
            >
              {{ Math.round(r.relevance * 100) }}%
            </span>
            <div class="flex-1 min-w-0">
              <p class="text-[13px] text-[var(--color-text-primary)]">{{ r.content }}</p>
              <p
                class="mt-0.5 text-[10px] text-[var(--color-text-tertiary)]"
                style="font-family: var(--font-mono)"
              >{{ formatRelative(r.createdAt) }}</p>
            </div>
            <button
              type="button"
              class="shrink-0 rounded p-1 text-[var(--color-text-tertiary)] opacity-0 transition-opacity hover:bg-[var(--color-error)]/10 hover:text-[var(--color-error)] group-hover:opacity-100"
              :aria-label="`删除 ${r.content}`"
              @click="deleteItem('relevant', r.id)"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- Preferences -->
    <section v-if="activeTab === 'preferences'" class="space-y-2">
      <div
        v-for="p in preferences"
        :key="p.id"
        class="group flex items-start gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
      >
        <span
          :class="[
            'shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider',
            p.kind === 'likes' ? 'bg-[var(--color-success)]/10 text-[var(--color-success)]' : 'bg-[var(--color-text-tertiary)]/10 text-[var(--color-text-tertiary)]',
          ]"
          style="font-family: var(--font-mono)"
        >{{ p.kind === 'likes' ? '喜欢' : '不喜欢' }}</span>
        <div class="flex-1 min-w-0">
          <p class="text-[13px] text-[var(--color-text-primary)]">{{ p.text }}</p>
          <div
            class="mt-1 flex items-center gap-3 text-[10px] text-[var(--color-text-tertiary)]"
            style="font-family: var(--font-mono)"
          >
            <span>强度 {{ Math.round(p.strength * 100) }}%</span>
            <span>·</span>
            <span>{{ formatRelative(p.createdAt) }}</span>
          </div>
        </div>
        <button
          type="button"
          class="shrink-0 rounded p-1 text-[var(--color-text-tertiary)] opacity-0 transition-opacity hover:bg-[var(--color-error)]/10 hover:text-[var(--color-error)] group-hover:opacity-100"
          :aria-label="`删除 ${p.text}`"
          @click="deleteItem('preferences', p.id)"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
    </section>

    <!-- Skills -->
    <section v-if="activeTab === 'skills'" class="space-y-2">
      <div
        v-for="s in skills"
        :key="s.id"
        class="group flex items-start gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
      >
        <span
          :class="[
            'shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium',
            s.source === 'auto-distilled' ? 'bg-[var(--color-brand)]/10 text-[var(--color-brand)]' : 'bg-[var(--color-surface-container)] text-[var(--color-text-secondary)]',
          ]"
          style="font-family: var(--font-mono)"
        >{{ s.source === 'auto-distilled' ? '自动提炼' : '手动创建' }}</span>
        <div class="flex-1 min-w-0">
          <p class="text-[13px] font-medium text-[var(--color-text-primary)]">{{ s.name }}</p>
          <p class="mt-0.5 text-[11px] text-[var(--color-text-secondary)]">{{ s.description }}</p>
          <p
            class="mt-1 text-[10px] text-[var(--color-text-tertiary)]"
            style="font-family: var(--font-mono)"
          >已用 {{ s.triggered }} 次</p>
        </div>
        <button
          type="button"
          class="shrink-0 rounded p-1 text-[var(--color-text-tertiary)] opacity-0 transition-opacity hover:bg-[var(--color-error)]/10 hover:text-[var(--color-error)] group-hover:opacity-100"
          :aria-label="`删除 ${s.name}`"
          @click="deleteItem('skills', s.id)"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
    </section>

    <!-- Trigger button (only on) -->
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
          :disabled="totalCount < 10"
          class="rounded-lg bg-[var(--color-brand)] px-4 py-2 text-[12px] font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          开始微调
        </button>
      </div>
    </div>

    <!-- Privacy banner -->
    <div class="rounded-lg border border-[var(--color-success)]/20 bg-[var(--color-success)]/5 p-3">
      <div class="flex items-center gap-3 text-[11px] text-[var(--color-text-tertiary)]">
        <span
          class="rounded bg-[var(--color-success)]/20 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-[var(--color-success)]"
          style="font-family: var(--font-mono)"
        >local only</span>
        <span>所有数据存储于本地。永远不会离开你的 Mac。</span>
      </div>
    </div>
  </div>
</template>
