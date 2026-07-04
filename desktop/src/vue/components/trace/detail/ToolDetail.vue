<script setup lang="ts">
// v3.0 — ToolDetail (trace detail, Vue 3)
// Direct translation — same Section usage, same meta grid.
import Section from './Section.vue'

const props = defineProps<{
  input?: string
  output?: string
  pending?: boolean
  toolUseId?: string
  status?: string
  startedAt?: string
  completedAt?: string
  durationMs?: number
}>()
</script>

<template>
  <div data-testid="trace-tool-detail">
    <Section v-if="input" section-key="tool.input" title="输入" :default-open="true">
      <pre class="font-[var(--font-mono)] text-xs leading-relaxed text-[var(--color-text-secondary)] whitespace-pre-wrap break-words max-h-[300px] overflow-auto">{{ input }}</pre>
    </Section>

    <Section section-key="tool.result" title="结果" :default-open="true">
      <div v-if="pending" class="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] px-3 py-3 text-xs text-[var(--color-text-tertiary)]">
        等待结果中…
      </div>
      <div v-else-if="output" class="font-[var(--font-mono)] text-xs leading-relaxed text-[var(--color-text-secondary)] whitespace-pre-wrap break-words max-h-[300px] overflow-auto">
        {{ output }}
      </div>
      <div v-else class="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] px-3 py-3 text-xs text-[var(--color-text-tertiary)]">
        无数据
      </div>
    </Section>

    <Section section-key="tool.meta" title="元信息">
      <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-[11px]">
        <template v-if="toolUseId">
          <dt class="font-medium text-[var(--color-text-tertiary)]">toolUseId</dt>
          <dd class="font-[var(--font-mono)] text-[var(--color-text-secondary)] truncate">{{ toolUseId }}</dd>
        </template>
        <dt class="font-medium text-[var(--color-text-tertiary)]">状态</dt>
        <dd :class="status === 'error' ? 'text-[var(--color-error)]' : status === 'pending' ? 'text-[var(--color-warning)]' : 'text-[var(--color-success)]'">{{ status === 'error' ? '错误' : status === 'pending' ? '等待中' : '成功' }}</dd>
        <template v-if="startedAt">
          <dt class="font-medium text-[var(--color-text-tertiary)]">开始时间</dt>
          <dd class="font-[var(--font-mono)] text-[var(--color-text-secondary)]">{{ startedAt }}</dd>
        </template>
        <template v-if="completedAt">
          <dt class="font-medium text-[var(--color-text-tertiary)]">完成时间</dt>
          <dd class="font-[var(--font-mono)] text-[var(--color-text-secondary)]">{{ completedAt }}</dd>
        </template>
        <template v-if="durationMs !== undefined">
          <dt class="font-medium text-[var(--color-text-tertiary)]">耗时</dt>
          <dd class="font-[var(--font-mono)] text-[var(--color-text-secondary)]">{{ durationMs }}ms</dd>
        </template>
      </dl>
    </Section>
  </div>
</template>
