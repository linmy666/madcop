<script setup lang="ts">
// v3.0 — MadCop Statusbar (Vue 3)
defineProps<{
  provider?: string
  model?: string
  sessionId?: string
  tokensUsed?: number
  tokensTotal?: number
  version?: string
}>()
</script>

<template>
  <div class="madcop-statusbar">
    <span class="madcop-statusbar__ok">●</span>
    <span>{{ provider || 'sensenova' }}</span>
    <span class="madcop-statusbar__sep">·</span>
    <span>{{ model || 'glm-5.2' }}</span>
    <span v-if="sessionId" class="madcop-statusbar__sep">·</span>
    <span v-if="sessionId" :title="sessionId">session {{ sessionId.slice(0, 8) }}</span>
    <span class="madcop-statusbar__spacer" />
    <span v-if="tokensTotal" :title="`${tokensUsed} / ${tokensTotal} tokens`">
      tokens {{ ((tokensUsed || 0) / 1000).toFixed(1) }}k / {{ (tokensTotal / 1000).toFixed(0) }}k
    </span>
    <span v-if="tokensTotal" class="madcop-statusbar__sep">·</span>
    <span>madcop {{ version || 'v3.0.0' }}</span>
  </div>
</template>

<style scoped>
.madcop-statusbar {
  width: 100%; height: 100%;
  display: flex; align-items: center;
  padding: 0 12px; gap: 12px;
  background: var(--madcop-panel-raised);
  color: var(--madcop-ink-muted);
  font-size: 11px; font-family: 'Geist Mono', monospace;
}
.madcop-statusbar__ok     { color: var(--madcop-success); }
.madcop-statusbar__sep    { color: var(--madcop-line); }
.madcop-statusbar__spacer { flex: 1; }
</style>
