<script setup lang="ts">
// ComputerUsePermissionModal — asks the user to approve a Computer Use
// (screen / accessibility) action the agent wants to perform.
// Displays the requested action and tool name; emits approve/close.
const props = defineProps<{
  sessionId?: string
  request?: {
    toolName?: string
    description?: string
    input?: unknown
  } | null
}>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'approve'): void }>()

function approve() { emit('approve') }
function deny() { emit('close') }
</script>

<template>
  <div v-if="request" class="cu-perm" role="dialog" aria-modal="true">
    <div class="cu-perm__card">
      <div class="cu-perm__head">
        <span class="material-symbols-outlined text-[24px] cu-perm__icon">desktop_windows</span>
        <div>
          <div class="cu-perm__title">Computer Use 权限请求</div>
          <div class="cu-perm__sub">Agent 想要操作你的电脑</div>
        </div>
      </div>

      <div v-if="request.toolName || request.description" class="cu-perm__detail">
        <div v-if="request.toolName" class="cu-perm__row">
          <span class="cu-perm__label">工具</span>
          <span class="cu-perm__value">{{ request.toolName }}</span>
        </div>
        <div v-if="request.description" class="cu-perm__row">
          <span class="cu-perm__label">操作</span>
          <span class="cu-perm__value">{{ request.description }}</span>
        </div>
        <div v-if="request.input" class="cu-perm__row">
          <span class="cu-perm__label">参数</span>
          <pre class="cu-perm__pre">{{ typeof request.input === 'string' ? request.input : JSON.stringify(request.input, null, 2) }}</pre>
        </div>
      </div>

      <div class="cu-perm__actions">
        <button class="cu-perm__btn cu-perm__btn--deny" @click="deny">拒绝</button>
        <button class="cu-perm__btn cu-perm__btn--approve" @click="approve">允许</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cu-perm {
  position: fixed; inset: 0; z-index: 200;
  display: flex; align-items: center; justify-content: center;
  background: var(--color-overlay-scrim);
}
.cu-perm__card {
  width: 420px; max-width: calc(100vw - 32px);
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius-lg); padding: 20px;
  box-shadow: var(--shadow-dropdown);
}
.cu-perm__head { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; }
.cu-perm__icon { color: var(--color-primary); }
.cu-perm__title { font-size: 15px; font-weight: 700; color: var(--color-text-primary); }
.cu-perm__sub { font-size: 12px; color: var(--color-text-secondary); margin-top: 2px; }
.cu-perm__detail { background: var(--color-surface-container-lowest); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: 12px; margin-bottom: 16px; }
.cu-perm__row { display: flex; gap: 8px; padding: 4px 0; font-size: 12px; }
.cu-perm__row + .cu-perm__row { border-top: 1px solid var(--color-border); margin-top: 4px; padding-top: 8px; }
.cu-perm__label { width: 40px; flex-shrink: 0; color: var(--color-text-tertiary); font-weight: 600; }
.cu-perm__value { color: var(--color-text-primary); }
.cu-perm__pre { margin: 0; flex: 1; font-family: var(--font-mono); font-size: 11px; color: var(--color-text-secondary); white-space: pre-wrap; word-break: break-word; max-height: 120px; overflow: auto; }
.cu-perm__actions { display: flex; gap: 8px; justify-content: flex-end; }
.cu-perm__btn { padding: 8px 20px; font-size: 13px; font-weight: 500; cursor: pointer; border-radius: var(--radius-md); border: 1px solid var(--color-border); }
.cu-perm__btn--deny { background: transparent; color: var(--color-text-secondary); }
.cu-perm__btn--deny:hover { background: var(--color-surface-hover); }
.cu-perm__btn--approve { background: var(--color-primary); color: var(--color-on-primary); border-color: var(--color-primary); }
.cu-perm__btn--approve:hover { opacity: 0.9; }
</style>
