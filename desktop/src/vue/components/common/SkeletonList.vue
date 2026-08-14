<script setup lang="ts">
/**
 * SkeletonList — loading placeholder that prevents layout jump (C-3).
 * Replaces "加载中…" text spinners on list surfaces. Each row is a
 * shimmer bar matching the typical list-item height.
 */
withDefaults(defineProps<{
  count?: number
  itemHeight?: number
}>(), {
  count: 5,
  itemHeight: 48,
})
</script>

<template>
  <div class="skeleton-list" role="status" aria-label="加载中">
    <div
      v-for="n in count" :key="n"
      class="skeleton-item"
      :style="{ height: itemHeight + 'px' }"
    >
      <div class="skeleton-avatar"></div>
      <div class="skeleton-lines">
        <div class="skeleton-line skeleton-line--w60"></div>
        <div class="skeleton-line skeleton-line--w40"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.skeleton-list { padding: 8px 0; }
.skeleton-item {
  display: flex; align-items: center; gap: 12px; padding: 8px 16px;
}
.skeleton-avatar {
  width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0;
  background: linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 75%);
  background-size: 200% 100%; animation: shimmer 1.5s infinite;
}
.skeleton-lines { flex: 1; display: flex; flex-direction: column; gap: 6px; }
.skeleton-line {
  height: 10px; border-radius: 4px;
  background: linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 75%);
  background-size: 200% 100%; animation: shimmer 1.5s infinite;
}
.skeleton-line--w60 { width: 60%; }
.skeleton-line--w40 { width: 40%; }
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
@media (prefers-reduced-motion: reduce) {
  .skeleton-avatar, .skeleton-line { animation: none; }
}
</style>
