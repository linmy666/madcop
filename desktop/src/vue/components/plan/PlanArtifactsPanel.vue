<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  workspaceDir?: string | null
  /** 最后完成步骤生成的文件路径，可选 */
  finalArtifact?: string | null
  /** 工作过程中间文件，可选 */
  workingFiles?: string[]
  /** 用到的技能/MCP tag */
  skillTags?: string[]
}>()

const emit = defineEmits<{
  (e: 'open', path: string): void
}>()

const parts = computed(() => {
  if (!props.workspaceDir) return []
  return props.workspaceDir.split('/').filter(Boolean)
})

const workingFilesList = computed(() => {
  return props.workingFiles || []
})

function basename(p: string): string {
  return p.split('/').pop() || p
}
</script>

<template>
  <aside class="artifacts-panel">
    <header class="ap__head">
      <h3 class="ap__title">产物</h3>
    </header>

    <div class="ap__body">
      <!-- Default working dir -->
      <section class="ap__section">
        <div class="ap__label">默认工作目录</div>
        <div class="ap__path-row" :title="workspaceDir || '(未设置)'">
          <svg class="ap__icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          <span class="ap__path">{{ workspaceDir || '~ 默认' }}</span>
        </div>
      </section>

      <!-- Final artifact -->
      <section class="ap__section">
        <div class="ap__label">最终交付</div>
        <div
          v-if="finalArtifact"
          class="ap__artifact ap__artifact--final"
          @click="emit('open', finalArtifact)"
          :title="finalArtifact"
        >
          <div class="ap__artifact-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <div class="ap__artifact-name">{{ basename(finalArtifact) }}</div>
        </div>
        <div v-else class="ap__empty">— 尚未生成</div>
      </section>

      <!-- Working files -->
      <section v-if="workingFilesList.length > 0" class="ap__section">
        <div class="ap__label">工作文件</div>
        <div class="ap__file-list">
          <div
            v-for="(file, i) in workingFilesList"
            :key="i"
            class="ap__artifact ap__artifact--working"
            @click="emit('open', file)"
            :title="file"
          >
            <div class="ap__artifact-icon">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
            </div>
            <div class="ap__artifact-name">{{ basename(file) }}</div>
          </div>
        </div>
      </section>

      <!-- Skills / MCP -->
      <section v-if="(skillTags && skillTags.length > 0)" class="ap__section">
        <div class="ap__label">技能</div>
        <div class="ap__skill-list">
          <div
            v-for="(tag, i) in skillTags"
            :key="i"
            class="ap__skill"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
            <span>{{ tag }}</span>
          </div>
        </div>
      </section>
    </div>
  </aside>
</template>

<style scoped>
.artifacts-panel {
  width: 100%;
  height: 100%;
  background: var(--color-surface, #fff);
  border-left: 1px solid var(--color-border, #e5e5e5);
  display: flex;
  flex-direction: column;
  font-size: 13px;
  color: var(--color-text-primary, #222);
}

.ap__head {
  padding: 14px 18px;
  border-bottom: 1px solid var(--color-border, #e5e5e5);
}
.ap__title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  letter-spacing: 0.2px;
  color: var(--color-text-primary, #222);
}

.ap__body {
  flex: 1;
  overflow-y: auto;
  padding: 6px 0 16px 0;
}

.ap__section {
  padding: 10px 0;
}

.ap__label {
  padding: 0 18px 6px 18px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-tertiary, #999);
  text-transform: uppercase;
  letter-spacing: 0.6px;
}

.ap__path-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 18px;
  font-size: 12px;
  color: var(--color-text-secondary, #555);
  font-family: ui-monospace, 'SF Mono', monospace;
}
.ap__icon {
  flex-shrink: 0;
  color: var(--color-text-tertiary, #999);
}
.ap__path {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ap__file-list {
  display: flex;
  flex-direction: column;
}

.ap__artifact {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 18px;
  cursor: pointer;
  transition: background 0.1s;
}
.ap__artifact:hover {
  background: var(--color-surface-container, #f5f5f5);
}

.ap__artifact-icon {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: var(--color-surface-container, #f0f0f0);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary, #555);
  flex-shrink: 0;
}

.ap__artifact--final .ap__artifact-icon {
  background: rgba(37, 99, 235, 0.08);
  color: #2563eb;
}

.ap__artifact-name {
  flex: 1;
  font-size: 12px;
  color: var(--color-text-primary, #222);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ap__empty {
  padding: 6px 18px;
  font-size: 12px;
  color: var(--color-text-tertiary, #888);
  font-style: italic;
}

.ap__skill-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 18px;
}

.ap__skill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background: var(--color-surface-container, #f5f5f5);
  border-radius: 4px;
  font-size: 11px;
  color: var(--color-text-secondary, #555);
  font-family: ui-monospace, 'SF Mono', monospace;
}
</style>