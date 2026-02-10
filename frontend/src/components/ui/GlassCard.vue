<script setup lang="ts">
defineProps<{ title?: string }>()
</script>

<template>
  <div class="glass-card">
    <h3 v-if="title">{{ title }}</h3>
    <slot />
  </div>
</template>
