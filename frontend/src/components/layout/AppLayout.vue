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
.layout { min-height: 100vh; }
.layout__main { padding: 1.5rem; max-width: 1280px; margin: 0 auto; }
</style>
