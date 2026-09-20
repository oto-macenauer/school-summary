<script setup lang="ts">
import AppHeader from './AppHeader.vue'
import PWAUpdate from './PWAUpdate.vue'
</script>

<template>
  <div class="layout">
    <AppHeader />
    <main class="layout__main">
      <slot />
    </main>
    <PWAUpdate />
  </div>
</template>

<style scoped>
.layout {
  min-height: 100vh;
  width: 100%;
  max-width: 100%;
  overflow-x: clip;
}

.layout__main {
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: var(--space-xl) var(--page-gutter);
  padding-left: max(var(--page-gutter), env(safe-area-inset-left));
  padding-right: max(var(--page-gutter), env(safe-area-inset-right));
  padding-bottom: max(var(--space-xl), env(safe-area-inset-bottom));
  /* Last line of defence: a runaway child scrolls nothing — the page never
     gains a horizontal scrollbar. */
  overflow-x: clip;
}

@media (max-width: 768px) {
  .layout__main { padding-top: var(--space-lg); }
}
</style>
