<script setup lang="ts">
import type { MarksData } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'

defineProps<{ data: MarksData | null }>()
</script>

<template>
  <GlassCard title="Známky">
    <template v-if="data">
      <div class="marks-header">
        <span class="average">Průměr: <strong>{{ data.overall_average?.toFixed(2) ?? '–' }}</strong></span>
        <span v-if="data.new_marks_count" class="badge badge--accent">{{ data.new_marks_count }} nových</span>
      </div>
      <div class="subjects">
        <div v-for="s in data.subjects" :key="s.name" class="subject">
          <span class="subject__name">{{ s.name }}</span>
          <span class="subject__new">
            <span v-if="s.new_marks" class="badge badge--accent">{{ s.new_marks }}</span>
          </span>
          <span class="subject__avg">{{ s.average?.toFixed(2) ?? '–' }}</span>
        </div>
      </div>
    </template>
    <p v-else class="empty">Známky nejsou k dispozici</p>
  </GlassCard>
</template>

<style scoped>
.marks-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-sm);
}
.average { font-size: var(--font-size-base); color: var(--text-secondary); }
.average strong { color: var(--text-primary); }
.subjects { display: flex; flex-direction: column; }
.subject {
  display: grid;
  grid-template-columns: 1fr 3rem 3.5rem;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
  font-size: var(--font-size-base);
  border-bottom: var(--border-subtle);
}
.subject:last-child { border-bottom: none; }
.subject__name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.subject__new { text-align: center; }
.subject__avg { color: var(--text-secondary); font-weight: var(--font-weight-medium); text-align: right; }
.empty { color: var(--text-muted); font-size: var(--font-size-base); }
</style>
