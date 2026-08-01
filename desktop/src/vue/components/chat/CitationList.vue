<script setup lang="ts">
/**
 * Sprint 4 — CitationList: renders the source citations collected by the
 * creation engine (DONE.metadata.citations). Shown below the streaming
 * assistant message. Each card has a number, title, and clickable URL.
 *
 * Anchor ids (`cite-N`) let the [n] markers in the article body link here.
 */
import type { PropType } from 'vue'

defineProps({
  citations: {
    type: Array as PropType<{ url: string; title: string; snippet: string }[]>,
    default: () => [],
  },
})
</script>

<template>
  <div v-if="citations.length > 0" class="cit-list">
    <h4 class="cit-title">
      <span class="material-symbols-outlined cit-title-icon">menu_book</span>
      参考来源
    </h4>
    <ol class="cit-items">
      <li
        v-for="(c, i) in citations"
        :key="i"
        :id="`cite-${i + 1}`"
        class="cit-item"
      >
        <span class="cit-num">{{ i + 1 }}</span>
        <div class="cit-body">
          <a
            :href="c.url"
            target="_blank"
            rel="noopener noreferrer"
            class="cit-link"
            :title="c.url"
          >{{ c.title || c.url }}</a>
          <p v-if="c.snippet" class="cit-snippet">{{ c.snippet }}</p>
          <span class="cit-url">{{ c.url }}</span>
        </div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.cit-list {
  margin: 8px 0 4px;
  padding: 12px 14px;
  background: var(--color-surface-container-low, #f7f7f8);
  border: 1px solid var(--color-border);
  border-radius: 10px;
}
.cit-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.cit-title-icon {
  font-size: 15px;
}
.cit-items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cit-item {
  display: flex;
  gap: 8px;
  padding: 6px 0;
  scroll-margin-top: 60px;
}
.cit-num {
  flex: none;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-brand, #0a0a0a);
  color: #fff;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 600;
}
.cit-body {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cit-link {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-brand, #2563eb);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cit-link:hover {
  text-decoration: underline;
}
.cit-snippet {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.cit-url {
  font-size: 11px;
  color: var(--color-text-tertiary);
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
