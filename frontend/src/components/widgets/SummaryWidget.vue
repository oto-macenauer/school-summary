<script setup lang="ts">
import { ref, computed } from 'vue'
import { marked } from 'marked'
import type { SummaryData } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'

const props = defineProps<{
  last: SummaryData | null
  current: SummaryData | null
  next: SummaryData | null
}>()

type Tab = 'last' | 'current' | 'next'
const activeTab = ref<Tab>('current')

const tabs: { key: Tab; label: string }[] = [
  { key: 'last', label: 'Minulý' },
  { key: 'current', label: 'Aktuální' },
  { key: 'next', label: 'Příští' },
]

const activeData = computed(() => {
  if (activeTab.value === 'last') return props.last
  if (activeTab.value === 'next') return props.next
  return props.current
})

const renderedText = computed(() => {
  if (!activeData.value?.summary_text) return ''
  return marked.parse(activeData.value.summary_text) as string
})

const dateRange = computed(() => {
  const d = activeData.value
  if (!d?.week_start || !d?.week_end) return ''
  const fmt = (s: string) => new Date(s).toLocaleDateString('cs')
  return `${fmt(d.week_start)} – ${fmt(d.week_end)}`
})
</script>

<template>
  <GlassCard title="Shrnutí týdne">
    <div class="summary-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="summary-tabs__btn"
        :class="{ 'summary-tabs__btn--active': activeTab === tab.key }"
        @click="activeTab = tab.key"
      >{{ tab.label }}</button>
    </div>
    <div v-if="activeData" class="summary">
      <div class="summary__text markdown-body" v-html="renderedText"></div>
      <span class="summary__meta">
        {{ dateRange }}
        <template v-if="activeData.generated_at"> · {{ new Date(activeData.generated_at).toLocaleString('cs') }}</template>
      </span>
    </div>
    <p v-else class="empty">Shrnutí zatím není k dispozici</p>
  </GlassCard>
</template>

<style scoped>
.summary-tabs { display: flex; gap: var(--space-xs); margin-bottom: var(--space-md); }
.summary-tabs__btn {
  padding: var(--space-xs) var(--space-md);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--transition);
}
.summary-tabs__btn:hover { color: var(--text-primary); background: rgba(255,255,255,0.04); }
.summary-tabs__btn--active {
  color: var(--text-primary);
  background: rgba(255,255,255,0.08);
  border-color: rgba(255,255,255,0.15);
}
.summary__text { font-size: var(--font-size-base); line-height: 1.6; }
.summary__text :deep(p) { margin: 0 0 0.5em; }
.summary__text :deep(ul) { margin: 0.25em 0; padding-left: 1.5em; }
.summary__text :deep(li) { margin: 0.15em 0; }
.summary__text :deep(li > ol) { list-style-type: none; }
.summary__text :deep(strong) { font-weight: 600; }
.summary__meta { display: block; margin-top: var(--space-md); font-size: var(--font-size-xs); color: var(--text-muted); }
.empty { color: var(--text-muted); font-size: var(--font-size-base); }
</style>
