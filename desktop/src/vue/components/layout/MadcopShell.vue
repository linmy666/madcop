<script setup lang="ts">
// v3.0 — MadCop Shell (Vue 3)
// Grid container with titlebar / sidebar / tabstrip / main / statusbar.
// The CSS-grid template mirrors the old .madcop-shell rule in
// theme/madcop.css.

import { useAppearance } from '../../composables/useAppearance'
useAppearance()  // re-render on theme change
</script>

<template>
  <div class="madcop-shell">
    <header v-if="$slots.titlebar" class="madcop-shell__titlebar">
      <slot name="titlebar" />
    </header>
    <aside v-if="$slots.sidebar" class="madcop-shell__sidebar">
      <slot name="sidebar" />
    </aside>
    <nav v-if="$slots.tabstrip" class="madcop-shell__tabstrip">
      <slot name="tabstrip" />
    </nav>
    <main class="madcop-shell__main">
      <slot />
    </main>
    <footer v-if="$slots.statusbar" class="madcop-shell__statusbar">
      <slot name="statusbar" />
    </footer>
  </div>
</template>
