<script setup lang="ts">
import { computed } from 'vue'
import Tooltip from '../common/Tooltip.vue'

const props = defineProps<{
  workspaceDir?: string | null
  /** 最后完成步骤生成的文件路径，可选 */
  finalArtifact?: string | null
  /** 工作过程中间文件，可选 */
  workingFiles?: string[]
  /** 用到的技能/MCP tag */
  skillTags?: string[]
  /** 当前会话标题 */
  sessionTitle?: string
}>()

const emit = defineEmits<{
  (e: 'open', path: string): void
  (e: 'close'): void
}>()

function basename(p: string): string {
  return p.split('/').pop() || p
}

const workingFilesList = computed(() => props.workingFiles || [])
</script>

<template>
  <aside class="artifacts-panel">
    <header class="ap__head">
      <div class="ap__head-left">
        <h3 class="ap__title">产物</h3>
        <span class="ap__count">{{ workingFilesList.length + 1 }}</span>
      </div>
      <Tooltip label="关闭产物面板">
        <button
          class="ap__close"
          type="button"
          title="关闭产物面板"
          aria-label="关闭产物面板"
          @click="emit('close')"
        >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
          <path d="M18 6 6 18" />
          <path d="m6 6 12 12" />
        </svg>
      </button>
      </Tooltip>
    </header>

    <div class="ap__body">
      <!-- Default working dir -->
      <section class="ap__section">
        <div class="ap__label">默认工作目录</div>
        <div class="ap__path-row" :title="workspaceDir || '(未设置)'">
          <svg class="ap__icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
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
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <div class="ap__artifact-name">{{ basename(finalArtifact) }}</div>
          <svg class="ap__chevron" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M9 18l6-6-6-6"/>
          </svg>
        </div>
        <div v-else class="ap__empty">
          <span class="ap__empty-dot"></span>
          尚未生成
        </div>
      </section>

      <!-- Working files -->
      <section v-if="workingFilesList.length > 0" class="ap__section">
        <div class="ap__label">工作文件</div>
        <div class="ap__file-list">
          <div
            v-for="(file, i) in workingFilesList"
            :key="i"
            class="ap__artifact"
            @click="emit('open', file)"
            :title="file"
          >
            <div class="ap__artifact-icon">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
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
            {{ tag }}
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
  background: var(--color-surface, #fcfcfd);
  border-left: 1px solid var(--color-border, #e8e8ec);
  display: flex;
  flex-direction: column;
  font-size: 13px;
  color: var(--color-text-primary, #1a1a1f);
  -webkit-font-smoothing: antialiased;
}

.ap__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border, #e8e8ec);
}
.ap__head-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ap__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  margin: -4px -4px -4px 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-tertiary, #999);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.ap__close:hover {
  background: var(--color-surface-container, #f0f0f2);
  color: var(--color-text-primary, #1a1a1f);
}
.ap__close:active {
  transform: scale(0.94);
}
.ap__title {
  font-size: 13px;
  font-weight: 600;
  margin: 0;
  letter-spacing: 0;
  color: var(--color-text-primary, #1a1a1f);
}
.ap__count {
  font-size: 10px;
  color: var(--color-text-tertiary, #999);
  font-family: var(--font-mono);
}

.ap__body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0 16px 0;
}

.ap__section {
  padding: 12px 0 4px 0;
}

.ap__label {
  padding: 0 16px 6px 16px;
  font-size: 10px;
  font-weight: 600;
  color: var(--color-text-tertiary, #888);
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

.ap__path-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  font-size: 12px;
  color: var(--color-text-secondary, #555);
  font-family: var(--font-mono);
  transition: background 0.1s;
}
.ap__path-row:hover {
  background: var(--color-surface-container, #f5f5f5);
}
.ap__icon {
  flex-shrink: 0;
  color: var(--color-text-tertiary, #888);
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
  padding: 7px 16px;
  cursor: pointer;
  transition: background 0.1s, transform 0.15s;
}
.ap__artifact:hover {
  background: var(--color-surface-container, #f5f5f5);
}
.ap__artifact:active {
  transform: scale(0.98);
}
.ap__artifact-icon {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: var(--color-surface-container, #f0f0f2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary, #888);
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s, transform 0.15s;
}
.ap__artifact:hover .ap__artifact-icon {
  transform: scale(1.05);
}

.ap__artifact--final .ap__artifact-icon {
  background: rgba(124, 58, 237, 0.10);
  color: var(--color-brand, #7C3AED);
}

.ap__artifact-name {
  flex: 1;
  font-size: 12px;
  color: var(--color-text-primary, #1a1a1f);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ap__chevron {
  flex-shrink: 0;
  color: var(--color-text-tertiary, #999);
}

.ap__empty {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  font-size: 12px;
  color: var(--color-text-tertiary, #999);
}
.ap__empty-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--color-text-tertiary, #d0d0d0);
  flex-shrink: 0;
}

.ap__skill-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 4px 16px 0 16px;
}

.ap__skill {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  background: var(--color-surface-container, #f0f0f2);
  border: 1px solid var(--color-border, #e8e8ec);
  border-radius: 999px;
  font-size: 11px;
  color: var(--color-text-secondary, #555);
}
</style>