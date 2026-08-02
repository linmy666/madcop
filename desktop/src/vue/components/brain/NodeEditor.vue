<script setup lang="ts">
/**
 * Sprint 6 — NodeEditor: create or edit a knowledge node.
 * Shown as a modal dialog. Emits `save` with the node payload, or `close`.
 */
import { ref, watch, computed } from 'vue'
import type { BrainNode } from '../../api/brain'

const props = defineProps<{
  /** When present, the editor is in "edit" mode (slug read-only). */
  existing?: BrainNode | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save', payload: { slug: string; title: string; body: string; type: string; tags: string[]; staleAfterDays?: number | null }): void
}>()

const isEdit = computed(() => !!props.existing)

const title = ref(props.existing?.title ?? '')
const slug = ref(props.existing?.slug ?? '')
const body = ref(props.existing?.body ?? '')
const type = ref(props.existing?.type ?? 'concept')
const tagsStr = ref((props.existing?.tags ?? []).join(', '))
const staleAfterDays = ref<string>(
  props.existing?.staleAfterDays != null ? String(props.existing.staleAfterDays) : '',
)
const error = ref('')

// Reset on open when switching targets.
watch(
  () => props.existing,
  (n) => {
    title.value = n?.title ?? ''
    slug.value = n?.slug ?? ''
    body.value = n?.body ?? ''
    type.value = n?.type ?? 'concept'
    tagsStr.value = (n?.tags ?? []).join(', ')
    staleAfterDays.value = n?.staleAfterDays != null ? String(n.staleAfterDays) : ''
    error.value = ''
  },
)

function autoSlug() {
  // Only auto-generate for new nodes whose slug is untouched.
  if (isEdit.value || slug.value.trim()) return
  // Backend SLUG_RE: ^[a-z0-9](?:[a-z0-9_-]{0,126}[a-z0-9])?$
  // → lowercase ASCII alphanumerics + _- only, no CJK, must start & end
  //   alphanumeric. Strip everything else, then collapse/trim separators.
  let s = title.value
    .toLowerCase()
    // drop any non-[a-z0-9_-] char (CJK, punctuation, spaces → removed)
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[^a-z0-9]+/, '')   // trim leading non-alphanumeric
    .replace(/[^a-z0-9]+$/, '')   // trim trailing non-alphanumeric
    .slice(0, 60)
  // Pure-CJK titles yield an empty slug → fall back to a stable random id
  // so the user never sees a "slug required" error from a valid title.
  if (!s) {
    s = `node-${Math.random().toString(36).slice(2, 8)}`
  }
  slug.value = s
}

function submit() {
  error.value = ''
  const finalSlug = slug.value.trim()
  const finalTitle = title.value.trim()
  if (!finalTitle) {
    error.value = '请填写标题'
    return
  }
  // Match backend SLUG_RE exactly: ^[a-z0-9](?:[a-z0-9_-]{0,126}[a-z0-9])?$
  // (no /i flag — lowercase only).
  if (!/^[a-z0-9](?:[a-z0-9_-]{0,126}[a-z0-9])?$/.test(finalSlug)) {
    error.value = '标识符(slug)只能是小写字母、数字、下划线和连字符，且以字母或数字开头；中文标题会自动生成英文标识'
    return
  }
  const tags = tagsStr.value
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
  const staleDays = staleAfterDays.value.trim()
  emit('save', {
    slug: finalSlug,
    title: finalTitle,
    body: body.value,
    type: type.value,
    tags,
    staleAfterDays: staleDays ? parseInt(staleDays, 10) : null,
  })
}

const TYPE_OPTIONS = [
  { value: 'concept', label: '概念' },
  { value: 'skill', label: '技能' },
  { value: 'project', label: '项目' },
  { value: 'person', label: '人物' },
  { value: 'event', label: '事件' },
]
</script>

<template>
  <Teleport to="body">
    <div class="ne-overlay" @click.self="emit('close')">
      <div class="ne-dialog" role="dialog" aria-modal="true">
        <header class="ne-head">
          <h2 class="ne-title">{{ isEdit ? '编辑节点' : '新建知识节点' }}</h2>
          <button class="ne-x" @click="emit('close')" aria-label="关闭">
            <span class="material-symbols-outlined">close</span>
          </button>
        </header>

        <form class="ne-form" @submit.prevent="submit">
          <div class="ne-row">
            <label class="ne-field ne-field--type">
              <span class="ne-label">类型</span>
              <select v-model="type" class="ne-input" :disabled="isEdit">
                <option v-for="o in TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </label>
            <label class="ne-field ne-field--title">
              <span class="ne-label">标题</span>
              <input v-model="title" class="ne-input" placeholder="一句话概括这条知识" @input="autoSlug" />
            </label>
          </div>

          <label class="ne-field">
            <span class="ne-label">Slug <span class="ne-hint">URL 标识，自动生成可改</span></span>
            <input v-model="slug" class="ne-input" :disabled="isEdit" placeholder="my-knowledge-node" />
          </label>

          <label class="ne-field">
            <span class="ne-label">正文</span>
            <textarea v-model="body" class="ne-input ne-textarea" rows="6" placeholder="详细描述这条知识（Markdown）…"></textarea>
          </label>

          <label class="ne-field">
            <span class="ne-label">标签 <span class="ne-hint">逗号分隔</span></span>
            <input v-model="tagsStr" class="ne-input" placeholder="例如：react, 前端, 性能" />
          </label>

          <label class="ne-field">
            <span class="ne-label">过期天数 <span class="ne-hint">留空=永不过期；超期节点在画布上灰显</span></span>
            <input v-model="staleAfterDays" type="number" min="1" class="ne-input" placeholder="例如 30" />
          </label>

          <p v-if="error" class="ne-error">{{ error }}</p>

          <div class="ne-actions">
            <button type="button" class="ne-btn" @click="emit('close')">取消</button>
            <button type="submit" class="ne-btn ne-btn--primary">{{ isEdit ? '保存' : '创建' }}</button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ne-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(2px);
}
.ne-dialog {
  width: min(560px, 92vw);
  max-height: 88vh;
  overflow-y: auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}
.ne-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px 12px;
  border-bottom: 1px solid var(--color-border);
}
.ne-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  color: var(--color-text-primary);
}
.ne-x {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-text-tertiary);
  border-radius: 6px;
}
.ne-x:hover {
  background: var(--color-surface-container);
  color: var(--color-text-primary);
}
.ne-x .material-symbols-outlined {
  font-size: 18px;
}
.ne-form {
  padding: 18px 20px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.ne-row {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 12px;
}
.ne-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.ne-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary);
}
.ne-hint {
  font-weight: 400;
  color: var(--color-text-tertiary);
  margin-left: 4px;
}
.ne-input {
  padding: 8px 11px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
  font-size: 13px;
  color: var(--color-text-primary);
  font-family: inherit;
  outline: none;
  transition: border-color 120ms;
}
.ne-input:focus {
  border-color: var(--color-text-tertiary);
}
.ne-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.ne-textarea {
  resize: vertical;
  min-height: 120px;
  line-height: 1.55;
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 12.5px;
}
.ne-error {
  margin: 0;
  padding: 8px 11px;
  background: #fee2e2;
  color: #b91c1c;
  border-radius: 6px;
  font-size: 12.5px;
}
.ne-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  padding-top: 6px;
  border-top: 1px solid var(--color-border);
}
.ne-btn {
  padding: 7px 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
  cursor: pointer;
  font-family: inherit;
  transition: background 120ms;
}
.ne-btn:hover {
  background: var(--color-surface-container-low);
}
.ne-btn--primary {
  background: var(--color-brand, #0a0a0a);
  color: #fff;
  border-color: var(--color-brand, #0a0a0a);
}
.ne-btn--primary:hover {
  background: #1f2937;
}
</style>
