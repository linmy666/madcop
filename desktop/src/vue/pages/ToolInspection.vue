<script setup lang="ts">
/**
 * ToolInspection — live tool registry browser (replaces mock page).
 */
import { ref, computed, onMounted } from 'vue'
import { getApiUrl } from '../api/client'

type ToolInfo = {
  name: string
  description: string
  parameters?: Record<string, any>
  source?: string
}

const tools = ref<ToolInfo[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const search = ref('')
const selected = ref<ToolInfo | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await fetch(getApiUrl('/api/tools'))
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    tools.value = Array.isArray(data?.tools) ? data.tools : []
    if (!selected.value && tools.value[0]) selected.value = tools.value[0]
  } catch (e: any) {
    error.value = e?.message || '加载失败'
    tools.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return tools.value
  return tools.value.filter(
    (t) =>
      t.name.toLowerCase().includes(q) ||
      (t.description || '').toLowerCase().includes(q),
  )
})

const paramJson = computed(() => {
  if (!selected.value?.parameters) return '{}'
  try {
    return JSON.stringify(selected.value.parameters, null, 2)
  } catch {
    return String(selected.value.parameters)
  }
})
</script>

<template>
  <div class="tools">
    <div class="tools__head">
      <div>
        <h1>工具检查</h1>
        <p class="sub">当前注册到 Agent 的工具（内置 + MCP），共 {{ tools.length }} 个。</p>
      </div>
      <button type="button" class="btn" :disabled="loading" @click="load">
        {{ loading ? '加载中…' : '刷新' }}
      </button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div class="tools__body">
      <aside class="list">
        <input v-model="search" class="search" placeholder="搜索工具…" />
        <button
          v-for="t in filtered"
          :key="t.name"
          type="button"
          :class="['row', selected?.name === t.name ? 'active' : '']"
          @click="selected = t"
        >
          <span class="name">{{ t.name }}</span>
          <span class="desc">{{ t.description }}</span>
        </button>
        <p v-if="!loading && filtered.length === 0" class="empty">暂无工具</p>
      </aside>

      <main v-if="selected" class="detail">
        <div class="detail__title">
          <h2>{{ selected.name }}</h2>
          <span class="badge">{{ selected.source || 'registry' }}</span>
        </div>
        <p class="detail__desc">{{ selected.description || '无描述' }}</p>
        <h3>Parameters schema</h3>
        <pre class="schema">{{ paramJson }}</pre>
      </main>
      <main v-else class="detail empty-detail">选择左侧工具查看参数 schema</main>
    </div>
  </div>
</template>

<style scoped>
.tools { flex: 1; overflow: hidden; display: flex; flex-direction: column; padding: 24px 28px; }
.tools__head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; gap: 12px; }
.tools__head h1 { margin: 0; font-size: 22px; font-weight: 700; color: var(--color-text-primary); }
.sub { margin: 4px 0 0; font-size: 13px; color: var(--color-text-secondary); }
.btn {
  padding: 6px 12px; border-radius: 8px; border: 1px solid var(--color-border);
  background: var(--color-surface); cursor: pointer; font-size: 13px;
  color: var(--color-text-primary);
}
.err { color: var(--color-error); font-size: 13px; margin-bottom: 12px; }
.tools__body { flex: 1; min-height: 0; display: grid; grid-template-columns: 280px 1fr; gap: 16px; }
.list {
  border: 1px solid var(--color-border); border-radius: 12px; overflow: auto;
  background: var(--color-surface); display: flex; flex-direction: column;
}
.search {
  margin: 10px; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--color-border);
  background: var(--color-surface-container-low); color: var(--color-text-primary); font-size: 13px;
}
.row {
  text-align: left; border: 0; border-top: 1px solid var(--color-border);
  background: transparent; padding: 10px 12px; cursor: pointer;
  display: flex; flex-direction: column; gap: 2px;
}
.row:hover { background: var(--color-sidebar-item-hover, rgba(0,0,0,0.03)); }
.row.active { background: var(--color-sidebar-item-active, rgba(124,58,237,0.08)); }
.name { font-size: 13px; font-weight: 600; color: var(--color-text-primary); font-family: ui-monospace, monospace; }
.desc {
  font-size: 11px; color: var(--color-text-tertiary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.empty { padding: 20px; text-align: center; color: var(--color-text-tertiary); font-size: 12px; }
.detail {
  border: 1px solid var(--color-border); border-radius: 12px; padding: 18px 20px;
  background: var(--color-surface); overflow: auto;
}
.detail__title { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.detail__title h2 { margin: 0; font-size: 18px; font-family: ui-monospace, monospace; }
.badge {
  font-size: 10px; padding: 2px 8px; border-radius: 999px;
  border: 1px solid var(--color-border); color: var(--color-text-secondary);
}
.detail__desc { font-size: 13px; color: var(--color-text-secondary); margin: 0 0 16px; }
.detail h3 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--color-text-tertiary); margin: 0 0 8px; }
.schema {
  margin: 0; padding: 12px; border-radius: 8px;
  background: var(--color-surface-container-low);
  font-size: 12px; line-height: 1.5; overflow: auto;
  color: var(--color-text-primary); white-space: pre-wrap;
}
.empty-detail { display: flex; align-items: center; justify-content: center; color: var(--color-text-tertiary); font-size: 13px; }
</style>
