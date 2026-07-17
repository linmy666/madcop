<script setup lang="ts">
/**
 * Compact topology diagram for preset cards (pure SVG, no broken nested markup).
 */
const props = defineProps<{
  kind: 'single' | 'chain' | 'parallel' | 'debate' | 'ensemble' | string
}>()
</script>

<template>
  <svg class="tmg" viewBox="0 0 200 88" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <defs>
      <linearGradient id="tmg-g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#7c3aed" stop-opacity="0.15"/>
        <stop offset="100%" stop-color="#7c3aed" stop-opacity="0.02"/>
      </linearGradient>
    </defs>
    <rect width="200" height="88" rx="10" fill="url(#tmg-g)"/>

    <!-- single -->
    <g v-if="kind === 'single'">
      <circle cx="100" cy="44" r="18" fill="#7c3aed"/>
      <circle cx="100" cy="44" r="18" fill="none" stroke="#c4b5fd" stroke-width="3" opacity="0.6"/>
      <text x="100" y="48" text-anchor="middle" fill="#fff" font-size="11" font-weight="700" font-family="system-ui">A</text>
    </g>

    <!-- chain -->
    <g v-else-if="kind === 'chain'">
      <line x1="40" y1="44" x2="160" y2="44" stroke="#c4b5fd" stroke-width="3" stroke-linecap="round"/>
      <circle cx="40" cy="44" r="14" fill="#7c3aed"/>
      <circle cx="100" cy="44" r="14" fill="#2563eb"/>
      <circle cx="160" cy="44" r="14" fill="#10b981"/>
      <text x="40" y="48" text-anchor="middle" fill="#fff" font-size="10" font-weight="700" font-family="system-ui">1</text>
      <text x="100" y="48" text-anchor="middle" fill="#fff" font-size="10" font-weight="700" font-family="system-ui">2</text>
      <text x="160" y="48" text-anchor="middle" fill="#fff" font-size="10" font-weight="700" font-family="system-ui">3</text>
    </g>

    <!-- parallel -->
    <g v-else-if="kind === 'parallel'">
      <line x1="36" y1="44" x2="80" y2="22" stroke="#c4b5fd" stroke-width="2.5"/>
      <line x1="36" y1="44" x2="80" y2="44" stroke="#c4b5fd" stroke-width="2.5"/>
      <line x1="36" y1="44" x2="80" y2="66" stroke="#c4b5fd" stroke-width="2.5"/>
      <line x1="120" y1="22" x2="164" y2="44" stroke="#c4b5fd" stroke-width="2.5"/>
      <line x1="120" y1="44" x2="164" y2="44" stroke="#c4b5fd" stroke-width="2.5"/>
      <line x1="120" y1="66" x2="164" y2="44" stroke="#c4b5fd" stroke-width="2.5"/>
      <circle cx="36" cy="44" r="12" fill="#7c3aed"/>
      <circle cx="100" cy="22" r="11" fill="#2563eb"/>
      <circle cx="100" cy="44" r="11" fill="#ec4899"/>
      <circle cx="100" cy="66" r="11" fill="#0891b2"/>
      <circle cx="164" cy="44" r="12" fill="#10b981"/>
    </g>

    <!-- debate -->
    <g v-else-if="kind === 'debate'">
      <path d="M55 30 Q100 10 145 30" stroke="#c4b5fd" stroke-width="2.5" fill="none" marker-end="url(#arr)"/>
      <path d="M145 58 Q100 78 55 58" stroke="#f9a8d4" stroke-width="2.5" fill="none"/>
      <line x1="55" y1="44" x2="145" y2="44" stroke="none"/>
      <line x1="100" y1="44" x2="100" y2="72" stroke="#fde68a" stroke-width="2"/>
      <circle cx="55" cy="44" r="14" fill="#7c3aed"/>
      <circle cx="145" cy="44" r="14" fill="#ec4899"/>
      <circle cx="100" cy="72" r="11" fill="#f59e0b"/>
      <text x="55" y="48" text-anchor="middle" fill="#fff" font-size="9" font-weight="700" font-family="system-ui">提</text>
      <text x="145" y="48" text-anchor="middle" fill="#fff" font-size="9" font-weight="700" font-family="system-ui">驳</text>
      <text x="100" y="76" text-anchor="middle" fill="#fff" font-size="9" font-weight="700" font-family="system-ui">判</text>
    </g>

    <!-- ensemble / default -->
    <g v-else>
      <line x1="30" y1="44" x2="70" y2="22" stroke="#c4b5fd" stroke-width="2"/>
      <line x1="30" y1="44" x2="70" y2="44" stroke="#c4b5fd" stroke-width="2"/>
      <line x1="30" y1="44" x2="70" y2="66" stroke="#c4b5fd" stroke-width="2"/>
      <line x1="130" y1="22" x2="170" y2="44" stroke="#c4b5fd" stroke-width="2"/>
      <line x1="130" y1="44" x2="170" y2="44" stroke="#c4b5fd" stroke-width="2"/>
      <line x1="130" y1="66" x2="170" y2="44" stroke="#c4b5fd" stroke-width="2"/>
      <circle cx="30" cy="44" r="11" fill="#7c3aed"/>
      <circle cx="100" cy="22" r="12" fill="#2563eb"/>
      <circle cx="100" cy="44" r="12" fill="#8b5cf6"/>
      <circle cx="100" cy="66" r="12" fill="#6366f1"/>
      <circle cx="170" cy="44" r="11" fill="#10b981"/>
    </g>
  </svg>
</template>

<style scoped>
.tmg {
  width: 100%;
  height: 88px;
  display: block;
  border-radius: 10px;
}
</style>
