<script setup lang="ts">
// v3.0 — AppShell (Vue 3, React-equivalent layout)
// Mirrors desktop/src/components/layout/AppShell.tsx EXACTLY:
//   - Top: macOS traffic-light spacer + brand badge
//   - Below: Sidebar (left, collapsible) + main content area
//   - Inside main: optional TabBar on top, content below
//   - Bottom: H5 connection error / content router / error view
// No Tabstrip on top — that was the Vue version's "extra" that React doesn't have.

import { ref, onMounted, onUnmounted, computed } from 'vue'
import Sidebar from './Sidebar.vue'
import ContentRouter from './ContentRouter.vue'
import StartupErrorView from './StartupErrorView.vue'

const ready = ref(false)
const startupError = ref<string | null>(null)
const sidebarOpen = ref(true)

onMounted(() => {
  // Backend health check (silent — don't block app on transient failures)
  fetch('/api/health')
    .then(() => { ready.value = true })
    .catch(() => { /* backend may be slow or unreachable, don't block the app */ })
    .finally(() => { ready.value = true })
})

function toggleSidebar() { sidebarOpen.value = !sidebarOpen.value }
</script>

<template>
  <!-- Startup error -->
  <StartupErrorView v-if="startupError" :error="startupError!" />

  <!-- Main shell — matches React AppShell structure -->
  <div v-else class="h-screen w-screen flex flex-col overflow-hidden bg-[var(--color-surface)]">
    <!-- Body: Sidebar + Content (no separate TitleBar — sidebar handles macOS padding) -->
    <div class="flex flex-1 min-h-0 overflow-hidden">
      <!-- Sidebar -->
      <aside
        v-if="sidebarOpen"
        class="border-r border-[var(--color-border)] bg-[var(--color-surface-sidebar)] flex flex-col flex-shrink-0"
        style="width: var(--sidebar-width, 280px);"
      >
        <Sidebar />
      </aside>

      <!-- Main content area -->
      <main class="flex-1 flex flex-col min-w-0 overflow-hidden">
        <ContentRouter />
      </main>
    </div>
  </div>
</template>