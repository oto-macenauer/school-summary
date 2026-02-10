<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useStudentStore } from '@/stores/student'
import { getMarks } from '@/api/client'
import GlassCard from '@/components/ui/GlassCard.vue'

const store = useStudentStore()
const marks = ref<any>(null)
const expanded = ref<Set<string>>(new Set())

async function load() {
  if (!store.current) return
  marks.value = await getMarks(store.current)
}

function toggle(name: string) {
  if (expanded.value.has(name)) {
    expanded.value.delete(name)
  } else {
    expanded.value.add(name)
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('cs')
}

function weightLabel(w: number): string {
  if (w <= 1) return ''
  return `×${w}`
}

onMounted(load)
watch(() => store.current, load)
</script>

<template>
  <div>
    <h2 class="page-title">
      Známky
      <span v-if="marks" class="page-title__sub">
        — průměr {{ marks.overall_average?.toFixed(2) ?? '–' }}
      </span>
    </h2>
    <div v-if="marks" class="subjects">
      <GlassCard
        v-for="s in marks.subjects"
        :key="s.name"
        class="subject-card"
        @click="toggle(s.name)"
      >
        <div class="subject-header">
          <div class="subject-info">
            <strong class="subject-name">{{ s.name }}</strong>
            <span class="subject-meta">{{ s.marks_count }} známek</span>
          </div>
          <div class="subject-right">
            <span v-if="s.new_marks" class="badge badge--accent">{{ s.new_marks }} nových</span>
            <span class="subject-avg">{{ s.average?.toFixed(2) ?? '–' }}</span>
            <span class="subject-chevron" :class="{ 'subject-chevron--open': expanded.has(s.name) }">&#9662;</span>
          </div>
        </div>

        <div v-if="expanded.has(s.name) && s.marks?.length" class="marks-list">
          <div
            v-for="m in s.marks"
            :key="m.id"
            class="mark-row"
            :class="{ 'mark-row--new': m.is_new }"
            @click.stop
          >
            <span class="mark-date">{{ formatDate(m.date) }}</span>
            <span class="mark-grade" :class="{ 'mark-grade--new': m.is_new }">{{ m.mark_text }}</span>
            <span class="mark-weight">{{ weightLabel(m.weight) }}</span>
            <span class="mark-caption">{{ m.caption }}</span>
            <span v-if="m.type_note" class="mark-type">{{ m.type_note }}</span>
          </div>
        </div>
        <div v-else-if="expanded.has(s.name)" class="marks-empty">
          Žádné známky
        </div>
      </GlassCard>
    </div>
  </div>
</template>

<style scoped>
.subjects { display: flex; flex-direction: column; gap: var(--space-sm); }

.subject-card { cursor: pointer; }

.subject-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.subject-info { display: flex; align-items: baseline; gap: var(--space-sm); }
.subject-name { font-size: var(--font-size-base); }
.subject-meta { color: var(--text-muted); font-size: var(--font-size-sm); }

.subject-right { display: flex; align-items: center; gap: var(--space-md); }
.subject-avg {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  min-width: 2.5rem;
  text-align: right;
}
.subject-chevron {
  color: var(--text-muted);
  font-size: var(--font-size-sm);
  transition: transform var(--transition);
}
.subject-chevron--open { transform: rotate(180deg); }

.marks-list {
  margin-top: var(--space-md);
  padding-top: var(--space-md);
  border-top: var(--border-subtle);
  display: flex;
  flex-direction: column;
}

.mark-row {
  display: grid;
  grid-template-columns: 5rem 2.5rem 2rem 1fr auto;
  gap: var(--space-sm);
  align-items: baseline;
  padding: var(--space-sm) 0;
  border-bottom: var(--border-subtle);
  font-size: var(--font-size-sm);
}
.mark-row:last-child { border-bottom: none; }
.mark-row--new { background: rgba(99, 102, 241, 0.04); border-radius: var(--radius-xs); }

.mark-date { color: var(--text-muted); }
.mark-grade {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  text-align: center;
}
.mark-grade--new { color: var(--accent); }
.mark-weight {
  color: var(--text-muted);
  font-size: var(--font-size-xs);
  text-align: center;
}
.mark-caption {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mark-type {
  color: var(--text-muted);
  font-size: var(--font-size-xs);
  white-space: nowrap;
}

.marks-empty {
  margin-top: var(--space-md);
  padding-top: var(--space-md);
  border-top: var(--border-subtle);
  color: var(--text-muted);
  font-size: var(--font-size-sm);
}

@media (max-width: 768px) {
  .mark-row {
    grid-template-columns: 4rem 2rem 1.5rem 1fr;
  }
  .mark-type { display: none; }
}
</style>
