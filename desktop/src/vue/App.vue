<script setup lang="ts">
// v3.0 — App.vue (Vue 3) — uses the new AppShell for React-equivalent layout
import { defineAsyncComponent } from 'vue'
import { useAppearance } from './composables/useAppearance'
import ErrorBoundary from './components/ErrorBoundary.vue'

useAppearance()

const AppShell = defineAsyncComponent(() => import('./components/layout/AppShell.vue'))
</script>

<template>
  <ErrorBoundary>
    <AppShell />
  </ErrorBoundary>
</template>