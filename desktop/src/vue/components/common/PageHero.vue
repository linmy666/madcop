<script setup lang="ts">
/**
 * PageHero — shared page header for all utility pages.
 *
 * Qoder-style structure: small eyebrow label, large title with an
 * accent-colored keyword, one-line subtitle, right-aligned actions.
 * Every list/settings page opens with this so the whole app shares
 * one design rhythm instead of per-page ad-hoc headers.
 */
defineProps<{
  eyebrow: string
  /** Plain title part before the accent word. */
  title: string
  /** Accent-colored keyword appended to the title. */
  accent?: string
  subtitle?: string
}>()
</script>

<template>
  <header class="page-hero">
    <div class="page-hero__text">
      <div class="page-hero__eyebrow">{{ eyebrow }}</div>
      <h2 class="page-hero__title">
        {{ title }}
        <span v-if="accent" class="page-hero__accent">{{ accent }}</span>
      </h2>
      <p v-if="subtitle" class="page-hero__subtitle">{{ subtitle }}</p>
    </div>
    <div class="page-hero__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin: 0 0 22px;
}
.page-hero__eyebrow {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: var(--color-text-tertiary);
  margin-bottom: 6px;
}
.page-hero__title {
  margin: 0 0 6px;
  font-family: var(--font-headline);
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--color-text-primary);
}
.page-hero__accent {
  color: var(--color-primary);
}
.page-hero__subtitle {
  margin: 0;
  font-size: 13.5px;
  color: var(--color-text-secondary);
}
.page-hero__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
</style>
