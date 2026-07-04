<script setup lang="ts">
// v3.0 — Terminal chrome (Vue 3)
// macOS-style window decoration. Used by terminal, bash results.
</script>

<template>
  <div :class="['terminal-chrome', $attrs.class]">
    <div class="terminal-chrome__titlebar">
      <div class="terminal-chrome__lights">
        <span class="terminal-chrome__light terminal-chrome__light--danger" />
        <span class="terminal-chrome__light terminal-chrome__light--warning" />
        <span class="terminal-chrome__light terminal-chrome__light--accent" />
      </div>
      <span v-if="title" class="terminal-chrome__title">{{ title }}</span>
    </div>
    <div class="terminal-chrome__body">
      <slot />
    </div>
  </div>
</template>

<script lang="ts">
// Separate <script> (no setup) to expose props for the parent <script setup>.
export default {
  inheritAttrs: false,
}
</script>

<style scoped>
.terminal-chrome {
  overflow: hidden;
  border: 1.5px solid var(--madcop-line);
  background: #1E1E1E;
}
.terminal-chrome__titlebar {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px;
  background: #2D2D2D;
  border-bottom: 1.5px solid #1A1A1A;
}
.terminal-chrome__lights { display: flex; gap: 6px; }
.terminal-chrome__light  { width: 10px; height: 10px; border-radius: 50%; display: block; }
.terminal-chrome__light--danger  { background: #FF5F57; }
.terminal-chrome__light--warning { background: #FEBC2E; }
.terminal-chrome__light--accent  { background: #28C840; }
.terminal-chrome__title {
  margin-left: 8px; font-size: 10px;
  color: #999; font-family: 'Geist Mono', monospace;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.terminal-chrome__body {
  background: #1E1E1E; color: #D4D4D4;
}
</style>
