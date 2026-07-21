<script setup lang="ts">
/**
 * RagDebugPanel — a small inspector for the modular RAG pipeline.
 *
 * For any user message it shows:
 *   • how the query rewriter split it into keyword variants
 *   • the top hits returned by the modular retriever
 *   • the route the 3-tier hybrid router assigned (target + tier + scores)
 *   • the rendered prompt-block that the chat handler would inject
 *
 * The component fetches all three in parallel so latency stays bounded
 * by the slowest endpoint, not the sum of all three.
 */
import { ref, computed, watch } from 'vue'

interface RagItem {
  layer: string
  score: number
  text: string
}

interface RouteDecision {
  target: string
  confidence: number
  tier: number
  rewrites: string[]
  all_scores: Record<string, number>
}

const props = defineProps<{
  query: string
  visible?: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const items = ref<RagItem[]>([])
const rewrites = ref<string[]>([])
const confidence = ref(0)
const promptBlock = ref('')
const decision = ref<RouteDecision | null>(null)

const isLoading = ref(false)
const error = ref<string | null>(null)

const tierLabel = computed(() => {
  if (!decision.value) return ''
  switch (decision.value.tier) {
    case 1: return 'regex'
    case 2: return 'embedding'
    case 3: return 'llm'
    default: return 'fallback'
  }
})

async function refresh(q: string) {
  const query = q.trim()
  if (!query) {
    items.value = []
    rewrites.value = []
    confidence.value = 0
    promptBlock.value = ''
    decision.value = null
    return
  }
  isLoading.value = true
  error.value = null
  try {
    const [retrieveRes, routeRes] = await Promise.all([
      fetch('/api/rag/retrieve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, limit: 5, format: 'prompt' }),
      }).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`retrieve ${r.status}`)))),
      fetch('/api/rag/route', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      }).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`route ${r.status}`)))),
    ])
    items.value = Array.isArray(retrieveRes.items) ? retrieveRes.items : []
    rewrites.value = Array.isArray(retrieveRes.rewrites) ? retrieveRes.rewrites : []
    confidence.value = Number(retrieveRes.confidence || 0)
    promptBlock.value = String(retrieveRes.prompt_block || '')
    decision.value = routeRes as RouteDecision
  } catch (e: any) {
    error.value = e?.message || String(e)
    items.value = []
    decision.value = null
  } finally {
    isLoading.value = false
  }
}

watch(
  () => [props.query, props.visible],
  ([q, v]) => {
    if (v !== false) refresh(String(q || ''))
  },
  { immediate: true },
)
</script>

<template>
  <div v-if="props.visible !== false" class="rag-debug" role="region" aria-label="RAG debug panel">
    <header class="rag-debug__header">
      <div class="rag-debug__title">
        <span class="material-symbols-outlined text-[18px]">psychology</span>
        <span>RAG 调试</span>
        <span v-if="isLoading" class="rag-debug__loading">…</span>
      </div>
      <button
        type="button"
        class="rag-debug__close"
        aria-label="关闭"
        @click="emit('close')"
      >
        <span class="material-symbols-outlined text-[16px]">close</span>
      </button>
    </header>

    <div v-if="error" class="rag-debug__error">{{ error }}</div>

    <section v-if="decision" class="rag-debug__section">
      <div class="rag-debug__label">路由</div>
      <div class="rag-debug__route">
        <span class="rag-debug__target">{{ decision.target }}</span>
        <span class="rag-debug__tier" :data-tier="decision.tier">
          tier {{ decision.tier }} ({{ tierLabel }})
        </span>
        <span class="rag-debug__conf">
          {{ Math.round(decision.confidence * 100) }}%
        </span>
      </div>
      <details v-if="Object.keys(decision.all_scores || {}).length" class="rag-debug__scores">
        <summary>all_scores</summary>
        <ul>
          <li v-for="(v, k) in decision.all_scores" :key="k">
            <code>{{ k }}</code>: {{ v.toFixed(3) }}
          </li>
        </ul>
      </details>
    </section>

    <section class="rag-debug__section">
      <div class="rag-debug__label">
        检索
        <span v-if="items.length" class="rag-debug__badge">{{ items.length }}</span>
        <span v-if="confidence" class="rag-debug__badge rag-debug__badge--alt">
          conf {{ confidence.toFixed(2) }}
        </span>
      </div>
      <div v-if="rewrites.length > 1" class="rag-debug__rewrites">
        <span
          v-for="(r, i) in rewrites"
          :key="i"
          class="rag-debug__chip"
        >{{ r }}</span>
      </div>
      <ol v-if="items.length" class="rag-debug__items">
        <li v-for="(it, i) in items" :key="i" class="rag-debug__item">
          <div class="rag-debug__item-meta">
            <span class="rag-debug__layer">{{ it.layer }}</span>
            <span class="rag-debug__score">{{ it.score.toFixed(3) }}</span>
          </div>
          <pre class="rag-debug__text">{{ it.text }}</pre>
        </li>
      </ol>
      <div v-else class="rag-debug__empty">（未命中）</div>
    </section>

    <section v-if="promptBlock" class="rag-debug__section">
      <div class="rag-debug__label">prompt_block</div>
      <pre class="rag-debug__prompt">{{ promptBlock }}</pre>
    </section>
  </div>
</template>

<style scoped>
.rag-debug {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e5e7);
  border-radius: 12px;
  font-size: 12px;
  color: var(--color-text-primary, #111);
  max-height: 360px;
  overflow: auto;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.05);
}
.rag-debug__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
.rag-debug__title {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-brand, #7c3aed);
}
.rag-debug__loading {
  font-size: 11px;
  color: var(--color-text-tertiary, #999);
}
.rag-debug__close {
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  color: var(--color-text-tertiary, #999);
}
.rag-debug__close:hover {
  background: var(--color-surface-hover, #f0f0f2);
}
.rag-debug__error {
  padding: 8px 10px;
  background: color-mix(in srgb, #ef4444 12%, transparent);
  color: #b91c1c;
  border-radius: 8px;
}
.rag-debug__section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rag-debug__label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-text-tertiary, #888);
}
.rag-debug__badge {
  background: var(--color-surface-container-low, #f5f5f7);
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 10px;
  font-weight: 600;
  color: var(--color-text-secondary, #555);
  text-transform: none;
}
.rag-debug__badge--alt {
  background: color-mix(in srgb, var(--color-brand, #7c3aed) 14%, transparent);
  color: var(--color-brand, #7c3aed);
}
.rag-debug__route {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.rag-debug__target {
  font-weight: 600;
  padding: 2px 10px;
  background: color-mix(in srgb, var(--color-brand, #7c3aed) 12%, transparent);
  color: var(--color-brand, #7c3aed);
  border-radius: 999px;
}
.rag-debug__tier {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--color-surface-container-low, #f5f5f7);
  color: var(--color-text-secondary, #555);
}
.rag-debug__tier[data-tier='1'] { background: color-mix(in srgb, #22c55e 18%, transparent); color: #166534; }
.rag-debug__tier[data-tier='2'] { background: color-mix(in srgb, #3b82f6 18%, transparent); color: #1d4ed8; }
.rag-debug__tier[data-tier='3'] { background: color-mix(in srgb, #f59e0b 18%, transparent); color: #b45309; }
.rag-debug__conf {
  margin-left: auto;
  font-weight: 600;
  color: var(--color-text-secondary, #555);
}
.rag-debug__scores summary {
  cursor: pointer;
  font-size: 11px;
  color: var(--color-text-tertiary, #888);
}
.rag-debug__scores ul {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px 12px;
}
.rag-debug__scores code {
  font-size: 11px;
  color: var(--color-text-secondary, #555);
}
.rag-debug__rewrites {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.rag-debug__chip {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--color-surface-container-low, #f5f5f7);
  color: var(--color-text-secondary, #555);
}
.rag-debug__items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rag-debug__item {
  border: 1px solid var(--color-border, #e5e5e7);
  border-radius: 8px;
  padding: 6px 8px;
  background: var(--color-surface-container-low, #fafafa);
}
.rag-debug__item-meta {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--color-text-tertiary, #888);
  margin-bottom: 2px;
}
.rag-debug__layer {
  font-weight: 600;
  color: var(--color-brand, #7c3aed);
}
.rag-debug__text {
  margin: 0;
  font-size: 11px;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--color-text-primary, #111);
}
.rag-debug__empty {
  font-size: 11px;
  color: var(--color-text-tertiary, #999);
  font-style: italic;
}
.rag-debug__prompt {
  margin: 0;
  font-size: 11px;
  line-height: 1.4;
  white-space: pre-wrap;
  background: var(--color-surface-container-low, #f5f5f7);
  padding: 6px 8px;
  border-radius: 6px;
}
</style>