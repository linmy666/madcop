<script setup lang="ts">
// Knowledge Base: manage documents, context, and memory for agents.
// Wired to the real /api/agents/knowledge backend (JSON-backed CRUD).

import { ref, computed, onMounted } from 'vue'
import { getApiUrl } from '../api/client'

interface KnowledgeItem {
  id: string
  title: string
  type: 'document' | 'url' | 'note' | 'code'
  content: string
  tags: string[]
  pinned: boolean
  createdAt?: number
}

const items = ref<KnowledgeItem[]>([])
const loading = ref(true)
const search = ref('')
const filterType = ref<'all' | KnowledgeItem['type']>('all')
const showAdd = ref(false)
const newItem = ref({
  title: '',
  type: 'note' as KnowledgeItem['type'],
  content: '',
  tags: '',
})

async function load() {
  loading.value = true
  try {
    const res = await fetch(getApiUrl('/api/agents/knowledge'))
    if (res.ok) {
      const data = await res.json()
      items.value = (data.items || []).map((i: any) => ({
        id: i.id,
        title: i.title || deriveTitle(i.content),
        type: (i.type || 'note') as KnowledgeItem['type'],
        content: i.content || '',
        tags: Array.isArray(i.tags) ? i.tags : [],
        pinned: !!i.pinned,
        createdAt: i.createdAt,
      }))
    }
  } catch {
    /* keep empty */
  } finally {
    loading.value = false
  }
}

function deriveTitle(content: string): string {
  const firstLine = (content || '').split('\n')[0].trim()
  return firstLine.slice(0, 60) || '未命名'
}

onMounted(load)

const filtered = computed(() => {
  let pool = items.value
  if (filterType.value !== 'all') {
    pool = pool.filter((i) => i.type === filterType.value)
  }
  const q = search.value.trim().toLowerCase()
  if (q) {
    pool = pool.filter(
      (i) =>
        i.title.toLowerCase().includes(q) ||
        i.tags.some((t) => t.toLowerCase().includes(q)) ||
        i.content.toLowerCase().includes(q)
    )
  }
  return [...pool].sort(
    (a, b) => Number(b.pinned) - Number(a.pinned) || (b.createdAt || 0) - (a.createdAt || 0)
  )
})

const typeIcons: Record<KnowledgeItem['type'], string> = {
  document: 'description',
  url: 'link',
  note: 'sticky_note_2',
  code: 'code',
}
const typeLabels: Record<KnowledgeItem['type'], string> = {
  document: '文档',
  url: '链接',
  note: '笔记',
  code: '代码',
}

async function togglePin(item: KnowledgeItem) {
  const next = !item.pinned
  item.pinned = next
  try {
    await fetch(getApiUrl(`/api/agents/knowledge/${item.id}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pinned: next }),
    })
  } catch {
    item.pinned = !next
  }
}

async function deleteItem(id: string) {
  if (!confirm('确定删除这条知识？')) return
  items.value = items.value.filter((i) => i.id !== id)
  try {
    await fetch(getApiUrl(`/api/agents/knowledge/${id}`), { method: 'DELETE' })
  } catch {}
}

async function addItem() {
  if (!newItem.value.title.trim() && !newItem.value.content.trim()) return
  const payload = {
    title: newItem.value.title.trim(),
    type: newItem.value.type,
    content: newItem.value.content,
    tags: newItem.value.tags
      ? newItem.value.tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean)
      : [],
    pinned: false,
  }
  try {
    const res = await fetch(getApiUrl('/api/agents/knowledge'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (res.ok) {
      const created = await res.json()
      items.value.unshift({
        ...created,
        title: created.title || payload.title,
        type: (created.type || payload.type) as KnowledgeItem['type'],
        tags: payload.tags,
        pinned: false,
      })
    }
  } catch {}
  newItem.value = { title: '', type: 'note', content: '', tags: '' }
  showAdd.value = false
}

const TYPE_FILTERS: Array<'all' | KnowledgeItem['type']> = [
  'all',
  'document',
  'note',
  'code',
  'url',
]
</script>

<template>
  <div class="kb-page">
    <div class="kb-page__inner">
      <!-- Header -->
      <header class="kb-page__head">
        <div>
          <h1 class="kb-page__title">知识库</h1>
          <p class="kb-page__sub">{{ items.length }} 个条目 · Agent 会话中可引用这些知识</p>
        </div>
        <button class="kb-btn kb-btn--primary" @click="showAdd = !showAdd">
          <span class="material-symbols-outlined" style="font-size:18px">{{ showAdd ? 'close' : 'add' }}</span>
          {{ showAdd ? '取消' : '添加知识' }}
        </button>
      </header>

      <!-- Add form -->
      <Transition name="kb-slide">
        <form v-if="showAdd" class="kb-add" @submit.prevent="addItem">
          <div class="kb-add__row">
            <label class="kb-add__field kb-add__field--type">
              <span class="kb-add__label">类型</span>
              <select v-model="newItem.type" class="kb-input">
                <option value="note">笔记</option>
                <option value="document">文档</option>
                <option value="url">链接</option>
                <option value="code">代码</option>
              </select>
            </label>
            <label class="kb-add__field kb-add__field--title">
              <span class="kb-add__label">标题</span>
              <input v-model="newItem.title" placeholder="一句话描述这条知识" class="kb-input" />
            </label>
          </div>
          <label class="kb-add__field">
            <span class="kb-add__label">标签 <span class="kb-add__hint">逗号分隔</span></span>
            <input v-model="newItem.tags" placeholder="例如：react, hooks, 前端" class="kb-input" />
          </label>
          <label class="kb-add__field">
            <span class="kb-add__label">内容</span>
            <textarea
              v-model="newItem.content"
              placeholder="详细描述或粘贴正文…"
              rows="5"
              class="kb-input kb-textarea"
            />
          </label>
          <div class="kb-add__actions">
            <button type="button" class="kb-btn" @click="showAdd = false">取消</button>
            <button type="submit" class="kb-btn kb-btn--primary" :disabled="!newItem.title.trim() && !newItem.content.trim()">
              保存
            </button>
          </div>
        </form>
      </Transition>

      <!-- Search + Filter -->
      <div class="kb-tools">
        <div class="kb-search">
          <span class="material-symbols-outlined kb-search__icon">search</span>
          <input
            v-model="search"
            placeholder="搜索标题、标签或内容…"
            class="kb-search__input"
          />
        </div>
        <div class="kb-filters">
          <button
            v-for="t in TYPE_FILTERS"
            :key="t"
            :class="['kb-filter', { 'kb-filter--active': filterType === t }]"
            @click="filterType = t"
          >{{ t === 'all' ? '全部' : typeLabels[t] }}</button>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="kb-skel-list">
        <div v-for="i in 3" :key="i" class="kb-skel-item">
          <div class="kb-skel-line kb-skel-line--icon"></div>
          <div class="kb-skel-body">
            <div class="kb-skel-line kb-skel-line--title"></div>
            <div class="kb-skel-line kb-skel-line--meta"></div>
          </div>
        </div>
      </div>

      <!-- List -->
      <div v-else-if="filtered.length > 0" class="kb-list">
        <article v-for="item in filtered" :key="item.id" class="kb-item">
          <div class="kb-item__icon">
            <span class="material-symbols-outlined">{{ typeIcons[item.type] }}</span>
          </div>
          <div class="kb-item__body">
            <div class="kb-item__head">
              <span class="kb-item__title">{{ item.title }}</span>
              <span v-if="item.pinned" class="material-symbols-outlined kb-item__pin">push_pin</span>
            </div>
            <div v-if="item.content" class="kb-item__excerpt">{{ item.content.slice(0, 200) }}{{ item.content.length > 200 ? '…' : '' }}</div>
            <div class="kb-item__meta">
              <span class="kb-item__type">{{ typeLabels[item.type] }}</span>
              <span class="kb-item__dot">·</span>
              <span class="kb-item__size">{{ item.content.length }} 字符</span>
              <span v-if="item.createdAt" class="kb-item__dot">·</span>
              <time v-if="item.createdAt" class="kb-item__date">{{ new Date(item.createdAt * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric' }) }}</time>
            </div>
            <div v-if="item.tags.length" class="kb-item__tags">
              <span v-for="tag in item.tags" :key="tag" class="kb-item__tag">#{{ tag }}</span>
            </div>
          </div>
          <div class="kb-item__actions">
            <button
              class="kb-item__btn"
              :title="item.pinned ? '取消置顶' : '置顶'"
              @click="togglePin(item)"
            >
              <span class="material-symbols-outlined">{{ item.pinned ? 'push_pin' : 'push_pin' }}</span>
            </button>
            <button class="kb-item__btn kb-item__btn--del" title="删除" @click="deleteItem(item.id)">
              <span class="material-symbols-outlined">delete</span>
            </button>
          </div>
        </article>
      </div>

      <!-- Empty -->
      <div v-else class="kb-empty">
        <div class="kb-empty__icon">
          <span class="material-symbols-outlined">folder_off</span>
        </div>
        <h3 class="kb-empty__title">知识库为空</h3>
        <p class="kb-empty__sub">点"添加知识"添加一条，或切换筛选条件重试</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Page layout ─────────────────────────────────────────────────── */
.kb-page { width: 100%; height: 100%; overflow-y: auto; background: var(--color-surface); }
.kb-page__inner { max-width: 880px; margin: 0 auto; padding: 48px 32px 64px; }

.kb-page__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 32px;
}
.kb-page__title {
  font-size: 28px;
  font-weight: 600;
  margin: 0 0 4px;
  letter-spacing: -0.01em;
  color: var(--color-text-primary);
}
.kb-page__sub {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary);
}

/* ── Buttons (shared) ────────────────────────────────────────────── */
.kb-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary);
  cursor: pointer;
  font-family: inherit;
  transition: background 120ms, border-color 120ms;
}
.kb-btn:hover { background: var(--color-surface-container-low); }
.kb-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.kb-btn--primary {
  background: var(--color-brand, #0a0a0a);
  color: #fff;
  border-color: var(--color-brand, #0a0a0a);
}
.kb-btn--primary:hover { background: #1f2937; border-color: #1f2937; }
.kb-btn--primary:disabled { background: var(--color-brand, #0a0a0a); }

/* ── Add form (slide-down) ───────────────────────────────────────── */
.kb-add {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.kb-add__row {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 12px;
}
.kb-add__field { display: flex; flex-direction: column; gap: 6px; }
.kb-add__field--title { flex: 1; }
.kb-add__label {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary);
}
.kb-add__hint {
  font-weight: 400;
  color: var(--color-text-tertiary);
  margin-left: 4px;
}
.kb-input {
  padding: 8px 12px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: var(--color-surface);
  font-size: 13px;
  color: var(--color-text-primary);
  font-family: inherit;
  outline: none;
  transition: border-color 120ms;
}
.kb-input:focus { border-color: var(--color-text-tertiary); }
.kb-textarea { resize: vertical; min-height: 80px; line-height: 1.5; }
.kb-add__actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  padding-top: 4px;
  border-top: 1px solid var(--color-border);
}

/* ── Search + filter chips ──────────────────────────────────────── */
.kb-tools {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.kb-search {
  flex: 1;
  min-width: 240px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: var(--color-surface);
  transition: border-color 120ms;
}
.kb-search:focus-within { border-color: var(--color-text-tertiary); }
.kb-search__icon { font-size: 16px; color: var(--color-text-tertiary); }
.kb-search__input {
  flex: 1;
  padding: 8px 0;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: var(--color-text-primary);
  font-family: inherit;
}
.kb-filters { display: flex; gap: 4px; flex-wrap: wrap; }
.kb-filter {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
  border-radius: 4px;
  font-family: inherit;
  transition: background 120ms, color 120ms, border-color 120ms;
}
.kb-filter:hover { color: var(--color-text-primary); }
.kb-filter--active {
  background: var(--color-text-primary);
  color: var(--color-surface);
  border-color: var(--color-text-primary);
}

/* ── Item list ─────────────────────────────────────────────────── */
.kb-list { display: flex; flex-direction: column; gap: 8px; }
.kb-item {
  display: grid;
  grid-template-columns: 40px 1fr auto;
  gap: 12px;
  padding: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  transition: border-color 140ms, background 140ms;
}
.kb-item:hover { border-color: var(--color-text-tertiary); background: var(--color-surface-container-lowest); }
.kb-item__icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-surface-container-low);
  color: var(--color-text-secondary);
  border-radius: 6px;
}
.kb-item__icon .material-symbols-outlined { font-size: 20px; }
.kb-item__body { min-width: 0; }
.kb-item__head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.kb-item__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kb-item__pin {
  font-size: 14px;
  color: var(--color-warning, #d97706);
}
.kb-item__excerpt {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin: 4px 0 8px;
  word-break: break-word;
}
.kb-item__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.kb-item__type {
  padding: 1px 6px;
  background: var(--color-surface-container);
  border-radius: 4px;
  font-weight: 500;
}
.kb-item__dot { opacity: 0.5; }
.kb-item__tags {
  display: flex;
  gap: 4px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.kb-item__tag {
  font-size: 11px;
  color: var(--color-text-tertiary);
  background: transparent;
  padding: 0;
}
.kb-item__actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-self: flex-start;
}
.kb-item__btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-text-tertiary);
  border-radius: 4px;
  transition: background 120ms, color 120ms;
}
.kb-item__btn:hover { background: var(--color-surface-container); color: var(--color-text-primary); }
.kb-item__btn .material-symbols-outlined { font-size: 16px; }
.kb-item__btn--del:hover { color: #b91c1c; background: #fee2e2; }

/* ── Loading skeleton ──────────────────────────────────────────── */
.kb-skel-list { display: flex; flex-direction: column; gap: 8px; }
.kb-skel-item {
  display: grid;
  grid-template-columns: 40px 1fr;
  gap: 12px;
  padding: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
}
.kb-skel-body { display: flex; flex-direction: column; gap: 8px; }
.kb-skel-line {
  height: 12px;
  background: var(--color-surface-container);
  border-radius: 4px;
  animation: kb-skel-pulse 1.4s ease-in-out infinite;
}
.kb-skel-line--icon { width: 40px; height: 40px; border-radius: 6px; }
.kb-skel-line--title { width: 40%; height: 14px; }
.kb-skel-line--meta { width: 70%; }
@keyframes kb-skel-pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 0.9; }
}

/* ── Empty state ───────────────────────────────────────────────── */
.kb-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 80px 24px;
  background: var(--color-surface-container-lowest);
  border: 1px dashed var(--color-border);
  border-radius: 12px;
  margin-top: 16px;
}
.kb-empty__icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--color-surface-container);
  margin-bottom: 16px;
}
.kb-empty__icon .material-symbols-outlined {
  font-size: 28px;
  color: var(--color-text-tertiary);
}
.kb-empty__title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 4px;
  color: var(--color-text-primary);
}
.kb-empty__sub {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}

/* ── Add form slide animation ──────────────────────────────────── */
.kb-slide-enter-active, .kb-slide-leave-active {
  transition: all 200ms ease;
  overflow: hidden;
}
.kb-slide-enter-from, .kb-slide-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
  margin-bottom: 0;
  border-width: 0;
}
</style>
