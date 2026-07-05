<script setup lang="ts">
// v3.0 — Knowledge Base: manage documents, context, and memory for agents.
// Agents can reference this knowledge during conversations.

import { ref, computed } from 'vue'

interface KnowledgeItem {
  id: string
  title: string
  type: 'document' | 'url' | 'note' | 'code'
  content: string
  tags: string[]
  size: string
  updatedAt: string
  pinned: boolean
}

const items = ref<KnowledgeItem[]>([
  { id: 'k1', title: 'MadCop 架构文档', type: 'document', content: '系统架构概览：Electron + Vue 3 + FastAPI...', tags: ['架构', '文档'], size: '24KB', updatedAt: '2026-07-04', pinned: true },
  { id: 'k2', title: 'Agent 设计模式', type: 'document', content: '12 种 Google Agent 设计模式的实现...', tags: ['agent', '模式'], size: '16KB', updatedAt: '2026-07-03', pinned: true },
  { id: 'k3', title: '菜鸟物流 API 文档', type: 'url', content: 'https://open.cainiao.com/docs', tags: ['工作', 'API'], size: '—', updatedAt: '2026-06-28', pinned: false },
  { id: 'k4', title: 'Vue 3 迁移笔记', type: 'note', content: 'React → Vue 3 翻译规则总结...', tags: ['前端', 'Vue'], size: '8KB', updatedAt: '2026-07-05', pinned: false },
  { id: 'k5', title: 'Python async 最佳实践', type: 'code', content: 'asyncio + aiohttp 模式...', tags: ['Python', '后端'], size: '12KB', updatedAt: '2026-06-20', pinned: false },
])

const search = ref('')
const filterType = ref<'all' | 'document' | 'url' | 'note' | 'code'>('all')
const showAdd = ref(false)
const newItem = ref({ title: '', type: 'note' as KnowledgeItem['type'], content: '', tags: '' })

const filtered = computed(() => {
  let pool = items.value
  if (filterType.value !== 'all') pool = pool.filter(i => i.type === filterType.value)
  const q = search.value.trim().toLowerCase()
  if (q) pool = pool.filter(i => i.title.toLowerCase().includes(q) || i.tags.some(t => t.includes(q)))
  // Pinned first
  return [...pool].sort((a, b) => Number(b.pinned) - Number(a.pinned))
})

const typeIcons: Record<string, string> = {
  document: 'description', url: 'link', note: 'sticky_note_2', code: 'code'
}
const typeLabels: Record<string, string> = {
  document: '文档', url: '链接', note: '笔记', code: '代码'
}

function togglePin(id: string) {
  const item = items.value.find(i => i.id === id)
  if (item) item.pinned = !item.pinned
}

function deleteItem(id: string) {
  items.value = items.value.filter(i => i.id !== id)
}

function addItem() {
  if (!newItem.value.title.trim()) return
  items.value.unshift({
    id: 'k' + Date.now(),
    title: newItem.value.title,
    type: newItem.value.type,
    content: newItem.value.content,
    tags: newItem.value.tags ? newItem.value.tags.split(',').map(t => t.trim()) : [],
    size: newItem.value.content.length + 'B',
    updatedAt: new Date().toISOString().slice(0, 10),
    pinned: false,
  })
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
              <span class="kb-item__type">{{ typeLabels[item.type] }}</span>
              <span class="kb-item__sep">·</span>
              <span class="kb-item__size">{{ item.size }}</span>
              <span class="kb-item__sep">·</span>
              <span class="kb-item__date">{{ item.updatedAt }}</span>
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