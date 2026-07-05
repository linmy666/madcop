<script setup lang="ts">
// v3.0 — MarkdownRenderer (Vue 3)
// Simple markdown-to-HTML renderer for release notes and inline markdown.
import { computed, type Ref } from 'vue'

const props = withDefaults(defineProps<{
  content: string
  variant?: 'inline' | 'document'
  class?: string
}>(), {
  variant: 'inline',
})

// Simple markdown to HTML: headers, bold, italic, code, links, lists, paragraphs.
function renderMarkdown(text: string): string {
  if (!text) return ''

  let html = text

  // Escape HTML entities
  html = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Code blocks (``` ... ```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre class="bg-[var(--color-surface-container-low)] rounded-lg p-3 overflow-x-auto"><code${lang ? ` class="language-${lang}"` : ''}>${code.trimEnd()}</code></pre>`
  })

  // Inline code (`...`)
  html = html.replace(/`([^`]+)`/g, '<code class="bg-[var(--color-surface-container-low)] px-1 py-0.5 rounded text-[11px]">$1</code>')

  // Bold (**text**)
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')

  // Italic (*text*)
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>')

  // Links [text](url)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-[var(--color-text-accent)] hover:underline">$1</a>')

  // Headers
  html = html.replace(/^### (.+)$/gm, '<h3 class="text-sm font-semibold mt-3 mb-1 text-[var(--color-text-primary)]">$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2 class="text-base font-semibold mt-4 mb-2 text-[var(--color-text-primary)]">$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1 class="text-lg font-bold mt-4 mb-2 text-[var(--color-text-primary)]">$1</h1>')

  // Bullet lists
  html = html.replace(/^[-*] (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
  html = html.replace(/(<li[^>]*>.*<\/li>)/g, '<ul class="my-1">$1</ul>')

  // Numbered lists
  html = html.replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>')

  // Horizontal rule
  html = html.replace(/^---$/gm, '<hr class="my-3 border-[var(--color-border)]" />')

  // Paragraphs (lines separated by blank lines)
  const blocks = html.split(/\n\n+/)
  html = blocks
    .map((block) => {
      const trimmed = block.trim()
      if (!trimmed) return ''
      if (trimmed.startsWith('<h') || trimmed.startsWith('<ul') || trimmed.startsWith('<pre') || trimmed.startsWith('<hr')) {
        return trimmed
      }
      return `<p>${trimmed.replace(/\n/g, '<br/>')}</p>`
    })
    .filter(Boolean)
    .join('\n')

  return html
}

const rendered = computed(() => renderMarkdown(props.content))
</script>

<template>
  <div
    :class="[
      'prose prose-sm',
      props.variant === 'document' && 'prose-p:text-sm',
      $props.class,
    ]"
    v-html="rendered"
  />
</template>
