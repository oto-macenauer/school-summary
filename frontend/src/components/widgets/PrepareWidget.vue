<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import type { PrepareData } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'

const props = defineProps<{ data: PrepareData | null; title?: string }>()

const renderedText = computed(() => {
  if (!props.data?.preparation_text) return ''
  return marked.parse(props.data.preparation_text) as string
})
</script>

<template>
  <GlassCard :title="title || 'Příprava'">
    <div v-if="data" class="prepare">
      <div class="prepare__text markdown-body" v-html="renderedText"></div>
      <span class="prepare__meta">{{ data.target_date ? new Date(data.target_date).toLocaleDateString('cs') : '' }}</span>
    </div>
    <p v-else class="empty">Příprava zatím není k dispozici</p>
  </GlassCard>
</template>

<style scoped>
.prepare__text { font-size: var(--font-size-base); line-height: 1.6; }
.prepare__text :deep(p) { margin: 0 0 0.5em; }
.prepare__text :deep(ul) { margin: 0.25em 0; padding-left: 1.5em; }
.prepare__text :deep(li) { margin: 0.15em 0; }
.prepare__text :deep(strong) { font-weight: 600; }
.prepare__meta { display: block; margin-top: var(--space-md); font-size: var(--font-size-xs); color: var(--text-muted); }
.empty { color: var(--text-muted); font-size: var(--font-size-base); }
</style>
