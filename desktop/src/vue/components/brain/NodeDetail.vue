<script setup lang="ts">
/**
 * Sprint 6 — NodeDetail: right-side drawer showing a node's full content,
 * tags and links, with edit / delete actions.
 */
import { computed } from 'vue'
import type { BrainNode } from '../../api/brain'

const props = defineProps<{
  node: BrainNode | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'edit', node: BrainNode): void
  (e: 'delete', slug: string): void
  (e: 'navigate', slug: string): void
  (e: 'deleteLink', fromSlug: string, toSlug: string): void
}>()

const TYPE_LABELS: Record<string, string> = {
  concept: '概念',
  skill: '技能',
  project: '项目',
  person: '人物',
  event: '事件',
}

const typeLabel = computed(() => (props.node ? TYPE_LABELS[props.node.type] ?? props.node.type : ''))

/** P2-1 — true when the node has a stale_after_days threshold AND its
 * last update is older than that threshold. */
const isStale = computed(() => {
  if (!props.node?.staleAfterDays) return false
  const updated = props.node.updatedAt ? new Date(props.node.updatedAt).getTime() : 0
  if (!updated) return false
  const ageDays = (Date.now() - updated) / 86400000
  return ageDays > props.node.staleAfterDays
})
</script>

<template>
  <Transition name="nd-slide">
    <aside v-if="node" class="nd-drawer" role="complementary" aria-label="节点详情">
      <header class="nd-head">
        <div class="nd-headtext">
          <span class="nd-type">{{ typeLabel }}</span>
          <h2 class="nd-title">{{ node.title }}</h2>
          <code class="nd-slug">{{ node.slug }}</code>
        </div>
        <button class="nd-x" @click="emit('close')" aria-label="关闭">
          <span class="material-symbols-outlined">close</span>
        </button>
      </header>

      <div class="nd-body">
        <div v-if="node.tags.length" class="nd-tags">
          <span v-for="tag in node.tags" :key="tag" class="nd-tag">#{{ tag }}</span>
        </div>

        <section v-if="node.body" class="nd-section">
          <h3 class="nd-h3">正文</h3>
          <pre class="nd-body-text">{{ node.body }}</pre>
        </section>
        <p v-else class="nd-empty-body">这个节点还没有正文内容。</p>

        <section v-if="node.linksOut && node.linksOut.length" class="nd-section">
          <h3 class="nd-h3">指向 ({{ node.linksOut.length }})</h3>
          <ul class="nd-links">
            <li v-for="l in node.linksOut" :key="l.slug">
              <button class="nd-link" @click="emit('navigate', l.slug)">
                <span class="material-symbols-outlined">arrow_forward</span>
                {{ l.slug }}
              </button>
              <span v-if="l.context" class="nd-link-ctx">{{ l.context }}</span>
              <button
                class="nd-link-del"
                title="删除此链接"
                @click="emit('deleteLink', node.slug, l.slug)"
              >
                <span class="material-symbols-outlined">link_off</span>
              </button>
            </li>
          </ul>
        </section>

        <section v-if="node.linksIn && node.linksIn.length" class="nd-section">
          <h3 class="nd-h3">被指向 ({{ node.linksIn.length }})</h3>
          <ul class="nd-links">
            <li v-for="l in node.linksIn" :key="l.slug">
              <button class="nd-link" @click="emit('navigate', l.slug)">
                <span class="material-symbols-outlined">arrow_back</span>
                {{ l.slug }}
              </button>
              <span v-if="l.context" class="nd-link-ctx">{{ l.context }}</span>
            </li>
          </ul>
        </section>

        <div class="nd-meta">
          <span v-if="node.createdAt">创建于 {{ new Date(node.createdAt).toLocaleString('zh-CN') }}</span>
          <span v-if="node.updatedAt">更新于 {{ new Date(node.updatedAt).toLocaleString('zh-CN') }}</span>
          <span v-if="isStale" class="nd-stale">⚠ 可能已过期（超过 {{ node.staleAfterDays }} 天未更新）</span>
          <span v-else-if="node.staleAfterDays">过期阈值：{{ node.staleAfterDays }} 天</span>
        </div>
      </div>

      <footer class="nd-foot">
        <button class="nd-action nd-action--del" @click="emit('delete', node.slug)">
          <span class="material-symbols-outlined">delete</span>
          删除
        </button>
        <button class="nd-action nd-action--edit" @click="emit('edit', node)">
          <span class="material-symbols-outlined">edit</span>
          编辑
        </button>
      </footer>
    </aside>
  </Transition>
</template>

<style scoped>
.nd-drawer {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 30;
  width: min(420px, 90vw);
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border-left: 1px solid var(--color-border);
  box-shadow: -8px 0 24px rgba(0, 0, 0, 0.08);
}
.nd-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 18px 14px;
  border-bottom: 1px solid var(--color-border);
}
.nd-headtext {
  min-width: 0;
}
.nd-type {
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  background: var(--color-surface-container);
  color: var(--color-text-secondary);
  border-radius: 4px;
  margin-bottom: 6px;
}
.nd-title {
  font-size: 17px;
  font-weight: 600;
  margin: 0 0 4px;
  color: var(--color-text-primary);
  line-height: 1.3;
}
.nd-slug {
  font-size: 11px;
  color: var(--color-text-tertiary);
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
}
.nd-x {
  flex: none;
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
.nd-x:hover {
  background: var(--color-surface-container);
  color: var(--color-text-primary);
}
.nd-x .material-symbols-outlined {
  font-size: 18px;
}
.nd-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.nd-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.nd-tag {
  font-size: 11px;
  color: var(--color-text-secondary);
  background: var(--color-surface-container-low);
  padding: 2px 8px;
  border-radius: 4px;
}
.nd-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.nd-h3 {
  font-size: 12px;
  font-weight: 600;
  margin: 0;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.nd-body-text {
  margin: 0;
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
.nd-empty-body {
  font-size: 13px;
  color: var(--color-text-tertiary);
  margin: 0;
}
.nd-links {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.nd-links li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.nd-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-brand, #2563eb);
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 12px;
  padding: 2px 4px;
  border-radius: 4px;
}
.nd-link:hover {
  background: var(--color-surface-container);
  text-decoration: underline;
}
.nd-link .material-symbols-outlined {
  font-size: 13px;
}
.nd-link-ctx {
  color: var(--color-text-tertiary);
  font-size: 11px;
}
.nd-link-del {
  margin-left: auto;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-text-tertiary);
  border-radius: 4px;
}
.nd-link-del:hover {
  background: #fee2e2;
  color: #b91c1c;
}
.nd-link-del .material-symbols-outlined {
  font-size: 14px;
}
.nd-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: var(--color-text-tertiary);
  padding-top: 8px;
  border-top: 1px solid var(--color-border);
}
.nd-stale {
  color: #b45309;
  font-weight: 600;
  margin-top: 2px;
}
.nd-foot {
  display: flex;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--color-border);
}
.nd-action {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  color: var(--color-text-primary);
  font-family: inherit;
  transition: background 120ms;
}
.nd-action:hover {
  background: var(--color-surface-container-low);
}
.nd-action .material-symbols-outlined {
  font-size: 16px;
}
.nd-action--del:hover {
  color: #b91c1c;
  border-color: #b91c1c;
}
.nd-action--edit {
  background: var(--color-brand, #0a0a0a);
  color: var(--color-on-primary, #fff);
  border-color: var(--color-brand, #0a0a0a);
}
.nd-action--edit:hover {
  background: #1f2937;
}

.nd-slide-enter-active,
.nd-slide-leave-active {
  transition: transform 220ms cubic-bezier(0.22, 1, 0.36, 1);
}
.nd-slide-enter-from,
.nd-slide-leave-to {
  transform: translateX(100%);
}
</style>
