<script setup lang="ts">
// Knowledge Base: manage documents, context, and memory for agents.
// Wired to the real /api/agents/knowledge backend (JSON-backed CRUD).

import { ref, computed, onMounted } from 'vue'
import { getApiUrl } from '../api/client'

interface KnowledgeItem {
  id: string
  title: string
  type: string            // 'document' | 'url' | 'note' | 'code' (free-form)
  content: string
  tags: string[]
  pinned: boolean
  createdAt?: number
}

const items = ref<KnowledgeItem[]>([])
const loading = ref(true)
const search = ref('')
const filterType = ref<'all' | 'document' | 'url' | 'note' | 'code'>('all')
const showAdd = ref(false)
const newItem = ref({ title: '', type: 'note' as KnowledgeItem['type'], content: '', tags: '' })

async function load() {
  loading.value = true
  try {
    const res = await fetch(getApiUrl('/api/agents/knowledge'))
    if (res.ok) {
      const data = await res.json()
      items.value = (data.items || []).map((i: any) => ({
        id: i.id,
        title: i.title || deriveTitle(i.content),
        type: i.type || 'note',
        content: i.content || '',
        tags: Array.isArray(i.tags) ? i.tags : [],
        pinned: !!i.pinned,
        createdAt: i.createdAt,
      }))
    }
  } catch { /* keep empty */ } finally { loading.value = false }
}

function deriveTitle(content: string): string {
  const firstLine = (content || '').split('\n')[0].trim()
  return firstLine.slice(0, 40) || '未命名'
}

onMounted(load)

const filtered = computed(() => {
  let pool = items.value
  if (filterType.value !== 'all') pool = pool.filter(i => i.type === filterType.value)
  const q = search.value.trim().toLowerCase()
  if (q) pool = pool.filter(i => i.title.toLowerCase().includes(q) || i.tags.some(t => t.toLowerCase().includes(q)) || i.content.toLowerCase().includes(q))
  return [...pool].sort((a, b) => Number(b.pinned) - Number(a.pinned) || (b.createdAt || 0) - (a.createdAt || 0))
})

const typeIcons: Record<string, string> = {
  document: 'description', url: 'link', note: 'sticky_note_2', code: 'code'
}
const typeLabels: Record<string, string> = {
  document: '文档', url: '链接', note: '笔记', code: '代码'
}

async function togglePin(item: KnowledgeItem) {
  const next = !item.pinned
  item.pinned = next
  try {
    await fetch(getApiUrl(`/api/agents/knowledge/${item.id}`), {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pinned: next }),
    })
  } catch { item.pinned = !next }
}

async function deleteItem(id: string) {
  items.value = items.value.filter(i => i.id !== id)
  try { await fetch(getApiUrl(`/api/agents/knowledge/${id}`), { method: 'DELETE' }) } catch {}
}

async function addItem() {
  if (!newItem.value.title.trim() && !newItem.value.content.trim()) return
  const payload = {
    title: newItem.value.title.trim(),
    type: newItem.value.type,
    content: newItem.value.content,
    tags: newItem.value.tags ? newItem.value.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
    pinned: false,
  }
  try {
    const res = await fetch(getApiUrl('/api/agents/knowledge'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (res.ok) {
      const created = await res.json()
      items.value.unshift({ ...created, title: created.title || payload.title, tags: payload.tags, pinned: false })
    }
  } catch {}
  newItem.value = { title: '', type: 'note', content: '', tags: '' }
  showAdd.value = false
}

const totalSize = computed(() => items.value.length)
</script>

<template>
  <div class="kb-page">
    <div class="kb-page__inner">
      <!-- Header -->
      <div class="kb-page__head">
        <div>
          <h1 class="kb-page__title">知识库</h1>
          <p class="kb-page__sub">{{ totalSize }} 个条目 · Agent 会话中可引用这些知识</p>
        </div>
        <button class="kb-page__add" @click="showAdd = !showAdd">
          <span class="material-symbols-outlined text-[18px]">{{ showAdd ? 'close' : 'add' }}</span>
          {{ showAdd ? '取消' : '添加知识' }}
        </button>
      </div>

      <!-- Add form -->
      <Transition name="kb-slide">
        <div v-if="showAdd" class="kb-add">
          <select v-model="newItem.type" class="kb-add__select">
            <option value="note">笔记</option>
            <option value="document">文档</option>
            <option value="url">链接</option>
            <option value="code">代码</option>
          </select>
          <input v-model="newItem.title" placeholder="标题…" class="kb-add__input" />
          <input v-model="newItem.tags" placeholder="标签 (逗号分隔)" class="kb-add__input" />
          <textarea v-model="newItem.content" placeholder="内容…" rows="3" class="kb-add__textarea" />
          <button class="kb-add__btn" @click="addItem">保存</button>
        </div>
      </Transition>

      <!-- Search + Filter -->
      <div class="kb-page__tools">
        <div class="kb-search">
          <span class="material-symbols-outlined text-[16px] text-[var(--color-text-tertiary)]">search</span>
          <input v-model="search" placeholder="搜索知识库…" class="kb-search__input" />
        </div>
        <div class="kb-filters">
          <button v-for="t in (['all', 'document', 'url', 'note', 'code'] as const)" :key="t"
            :class="['kb-filter', { 'kb-filter--active': filterType === t }]"
            @click="filterType = t"
          >{{ t === 'all' ? '全部' : typeLabels[t] }}</button>
        </div>
      </div>

      <!-- List -->
      <div class="kb-list">
        <div v-for="item in filtered" :key="item.id" class="kb-item">
          <div class="kb-item__icon">
            <span class="material-symbols-outlined text-[20px]">{{ typeIcons[item.type] }}</span>
          </div>
          <div class="kb-item__body">
            <div class="kb-item__title-row">
              <span class="kb-item__title">{{ item.title }}</span>
              <span v-if="item.pinned" class="material-symbols-outlined text-[14px] text-[var(--color-warning)]">push_pin</span>
            </div>
            <div class="kb-item__meta">
              <span class="kb-item__type">{{ typeLabels[item.type] || item.type }}</span>
              <span class="kb-item__sep">·</span>
              <span class="kb-item__size">{{ item.content.length }}B</span>
              <span class="kb-item__sep">·</span>
              <span class="kb-item__date">{{ item.createdAt ? new Date(item.createdAt * 1000).toLocaleDateString() : '—' }}</span>
            </div>
            <div class="kb-item__tags">
              <span v-for="tag in item.tags" :key="tag" class="kb-item__tag">{{ tag }}</span>
            </div>
          </div>
          <div class="kb-item__actions">
            <button class="kb-item__btn" @click="togglePin(item.id)" :title="item.pinned ? '取消置顶' : '置顶'">
              <span class="material-symbols-outlined text-[16px]">{{ item.pinned ? 'push_pin' : 'bookmark' }}</span>
            </button>
            <button class="kb-item__btn kb-item__btn--del" @click="deleteItem(item.id)" title="删除">
              <span class="material-symbols-outlined text-[16px]">delete</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Empty -->
      <div v-if="filtered.length === 0" class="kb-empty">
        <span class="material-symbols-outlined text-[48px] text-[var(--color-text-tertiary)]">folder_off</span>
        <p>知识库为空。点击「添加知识」开始。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kb-page { width: 100%; height: 100%; overflow-y: auto; background: var(--color-surface); }
.kb-page__inner { max-width: 800px; margin: 0 auto; padding: 24px 20px; }

.kb-page__head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.kb-page__title { font-size: 22px; font-weight: 700; color: var(--color-text-primary); margin: 0; }
.kb-page__sub { font-size: 12px; color: var(--color-text-secondary); margin-top: 4px; }
.kb-page__add {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 16px; font-size: 13px; font-weight: 500; cursor: pointer;
  background: var(--color-primary); color: var(--color-on-primary); border: none;
}

.kb-add {
  background: var(--color-surface-container-lowest); border: 1.5px solid var(--color-border);
  padding: 16px; margin-bottom: 16px; display: flex; flex-direction: column; gap: 8px;
}
.kb-add__select, .kb-add__input { padding: 8px 12px; border: 1px solid var(--color-border); background: var(--color-surface); font-size: 13px; color: var(--color-text-primary); outline: none; }
.kb-add__textarea { padding: 8px 12px; border: 1px solid var(--color-border); background: var(--color-surface); font-size: 13px; color: var(--color-text-primary); outline: none; resize: vertical; font-family: inherit; }
.kb-add__btn { padding: 8px 20px; background: var(--color-primary); color: var(--color-on-primary); border: none; cursor: pointer; font-size: 13px; font-weight: 500; align-self: flex-end; }

.kb-page__tools { display: flex; gap: 12px; margin-bottom: 16px; }
.kb-search { flex: 1; display: flex; align-items: center; gap: 8px; padding: 8px 12px; border: 1.5px solid var(--color-border); background: var(--color-surface-container-lowest); }
.kb-search__input { flex: 1; border: none; outline: none; background: transparent; font-size: 13px; color: var(--color-text-primary); }
.kb-filters { display: flex; gap: 4px; }
.kb-filter { padding: 6px 12px; font-size: 12px; cursor: pointer; background: transparent; border: 1px solid var(--color-border); color: var(--color-text-secondary); }
.kb-filter--active { background: var(--color-primary-fixed); color: var(--color-primary); border-color: var(--color-primary); }

.kb-list { display: flex; flex-direction: column; gap: 8px; }
.kb-item { display: flex; gap: 12px; padding: 14px 16px; background: var(--color-surface-container-lowest); border: 1px solid var(--color-border); transition: border-color 140ms; }
.kb-item:hover { border-color: var(--color-primary); }
.kb-item__icon { width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; background: var(--color-surface-container-high); color: var(--color-text-secondary); }
.kb-item__body { flex: 1; min-width: 0; }
.kb-item__title-row { display: flex; align-items: center; gap: 6px; }
.kb-item__title { font-size: 14px; font-weight: 600; color: var(--color-text-primary); }
.kb-item__meta { display: flex; align-items: center; gap: 6px; margin-top: 4px; font-size: 11px; color: var(--color-text-tertiary); }
.kb-item__sep { opacity: 0.5; }
.kb-item__tags { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }
.kb-item__tag { padding: 2px 6px; font-size: 10px; font-weight: 500; background: var(--color-primary-fixed); color: var(--color-primary); }
.kb-item__actions { display: flex; flex-direction: column; gap: 4px; }
.kb-item__btn { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; background: transparent; border: none; cursor: pointer; color: var(--color-text-tertiary); transition: color 140ms; }
.kb-item__btn:hover { color: var(--color-text-primary); }
.kb-item__btn--del:hover { color: var(--color-error); }

.kb-empty { text-align: center; padding: 60px 20px; color: var(--color-text-secondary); font-size: 14px; }
.kb-empty span { display: block; margin-bottom: 12px; }

.kb-slide-enter-active, .kb-slide-leave-active { transition: all 200ms; overflow: hidden; }
.kb-slide-enter-from, .kb-slide-leave-to { opacity: 0; max-height: 0; padding: 0; margin: 0; border: none; }
</style>