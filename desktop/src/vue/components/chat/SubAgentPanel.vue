<script setup lang="ts">
// SubAgentPanel — renders multiple sub-agents executing in parallel during
// deep mode. Each agent gets its own colored mascot + streaming text area,
// so the user sees several sprites "thinking" at once (like the multi-task
// stream view in Codex/Claude Code).
//
// Reads `agents` (a reactive map agent_id → { name, color, text, status })
// from the session state maintained by chatStore's agent_* SSE handlers.
import { computed } from 'vue'
import MascotAvatar from '../common/MascotAvatar.vue'

interface AgentStream {
  name: string
  color: string
  text: string
  status: 'running' | 'done' | 'error'
  elapsed_ms?: number
}

const props = defineProps<{ agents: Record<string, AgentStream> }>()

// Preserve insertion order (first-seen) so agents don't jump around as
// new ones start. Vue 3 reactivity preserves Map/obj insertion order for
// string keys, so Object.values is stable here.
const agentList = computed(() => Object.values(props.agents))
const activeCount = computed(() => agentList.value.filter(a => a.status === 'running').length)
</script>

<template>
  <div v-if="agentList.length" class="sub-agent-panel">
    <div class="sub-agent-panel__head">
      <span class="material-symbols-outlined text-[15px]">hub</span>
      <span class="sub-agent-panel__title">
        {{ activeCount > 0 ? `${activeCount} 个智能体协作中` : '协作完成' }}
      </span>
    </div>
    <div class="sub-agent-panel__grid">
      <div
        v-for="agent in agentList"
        :key="agent.name"
        class="sub-agent-card"
        :class="{ 'sub-agent-card--done': agent.status !== 'running' }"
      >
        <div class="sub-agent-card__head">
          <MascotAvatar :size="22" :color="agent.color" />
          <span class="sub-agent-card__name" :style="{ color: agent.color }">{{ agent.name }}</span>
          <span
            v-if="agent.status === 'running'"
            class="material-symbols-outlined text-[13px] sub-agent-card__spin"
          >progress_activity</span>
          <span v-else-if="agent.status === 'error'" class="sub-agent-card__badge sub-agent-card__badge--err">失败</span>
          <span v-else class="sub-agent-card__badge">完成</span>
        </div>
        <div class="sub-agent-card__body">
          <p class="sub-agent-card__text">{{ agent.text || '…' }}</p>
          <span
            v-if="agent.status === 'running' && agent.text"
            class="sub-agent-card__caret"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sub-agent-panel {
  margin: 12px 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface-container-lowest);
  overflow: hidden;
}
.sub-agent-panel__head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--color-surface-container-low);
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border);
}
.sub-agent-panel__head .material-symbols-outlined { color: var(--color-primary); }
.sub-agent-panel__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1px;
  background: var(--color-border); /* acts as the divider between cards */
}
.sub-agent-card {
  background: var(--color-surface-container-lowest);
  padding: 12px;
  min-width: 0;
  transition: opacity 200ms;
}
.sub-agent-card--done { opacity: 0.72; }
.sub-agent-card__head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.sub-agent-card__name {
  font-size: 13px;
  font-weight: 600;
  flex: 1;
  min-width: 0;
}
.sub-agent-card__spin {
  color: var(--color-primary);
  animation: sub-agent-spin 0.8s linear infinite;
}
@keyframes sub-agent-spin { to { transform: rotate(360deg); } }
.sub-agent-card__badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  background: var(--color-success);
  color: #fff;
}
.sub-agent-card__badge--err { background: var(--color-error); }
.sub-agent-card__body {
  position: relative;
  max-height: 200px;
  overflow-y: auto;
}
.sub-agent-card__text {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}
.sub-agent-card__caret {
  display: inline-block;
  width: 2px;
  height: 13px;
  background: var(--color-primary);
  vertical-align: text-bottom;
  margin-left: 1px;
  animation: sub-agent-breathe 1s ease-in-out infinite;
}
@keyframes sub-agent-breathe { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
</style>
