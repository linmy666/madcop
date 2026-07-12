<template>
  <span class="mc-tooltip-wrap" :class="{ 'mc-tooltip-wrap--full': full }">
    <slot />
    <span
      v-if="label"
      class="mc-tooltip"
      :class="`mc-tooltip--${placement}`"
      role="tooltip"
    >{{ label }}</span>
  </span>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    label?: string
    placement?: 'top' | 'bottom'
    full?: boolean
  }>(),
  { label: '', placement: 'top', full: false },
)
</script>

<style scoped>
.mc-tooltip-wrap {
  position: relative;
  display: inline-flex;
}
.mc-tooltip-wrap--full {
  display: flex;
  width: 100%;
}

.mc-tooltip {
  position: absolute;
  left: 50%;
  z-index: 9999;
  padding: 5px 9px;
  border-radius: 7px;
  background: var(--color-inverse-surface, #2f312e);
  color: var(--color-inverse-on-surface, #f2f1ed);
  font-size: 12px;
  line-height: 1.4;
  font-weight: 500;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: var(--shadow-dropdown, 0 8px 24px rgba(0, 0, 0, 0.25));
  opacity: 0;
  transform: translateX(-50%) translateY(2px) scale(0.98);
  transition: opacity 0.13s ease, transform 0.13s ease;
}

.mc-tooltip--top {
  bottom: calc(100% + 7px);
}
.mc-tooltip--bottom {
  top: calc(100% + 7px);
}

.mc-tooltip-wrap:hover .mc-tooltip,
.mc-tooltip-wrap:focus-within .mc-tooltip {
  opacity: 1;
  transform: translateX(-50%) translateY(0) scale(1);
}
</style>
