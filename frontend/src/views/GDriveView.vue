<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { marked } from 'marked'
import { useStudentStore } from '@/stores/student'
import { getGDriveReports } from '@/api/client'
import type { GDriveReport } from '@/types'

const store = useStudentStore()
const reports = ref<GDriveReport[]>([])
const expanded = ref<Set<number>>(new Set())
const search = ref('')

async function load() {
  if (!store.current) return
  const result = await getGDriveReports(store.current)
  reports.value = result.reports
}

function toggle(week: number) {
  if (expanded.value.has(week)) {
    expanded.value.delete(week)
  } else {
    expanded.value.add(week)
  }
}

function renderMd(text: string): string {
  return marked.parse(text) as string
}

const filtered = computed(() => {
  const q = search.value.toLowerCase().trim()
  if (!q) return reports.value
  return reports.value.filter(r =>
    r.content.toLowerCase().includes(q) ||
    r.source_file.toLowerCase().includes(q) ||
    `week ${r.week_number}`.includes(q) ||
    `týden ${r.week_number}`.includes(q)
  )
})

onMounted(load)
watch(() => store.current, load)
</script>

<template>
  <div>
    <h2 class="page-title">
      Týdenní reporty
      <span v-if="reports.length" class="badge badge--accent" style="margin-left: var(--space-sm);">
        {{ reports.length }} reportů
      </span>
    </h2>
    <div v-if="reports.length" class="search-bar">
      <input
        v-model="search"
        type="text"
        class="search-input glass-btn"
        placeholder="Hledat v reportech…"
      />
      <span v-if="search" class="search-count">{{ filtered.length }} výsledků</span>
    </div>
    <div v-if="reports.length" class="timeline">
      <div v-for="r in filtered" :key="r.week_number" class="timeline__day">
        <div class="timeline__date-col">
          <span class="timeline__date">Týden {{ r.week_number }}</span>
          <div class="timeline__line"></div>
        </div>
        <div class="timeline__messages">
          <div
            class="report inner-card"
            :class="{ 'report--expanded': expanded.has(r.week_number) }"
            @click="toggle(r.week_number)"
          >
            <div class="report__header">
              <strong class="report__title">{{ r.source_file }}</strong>
              <span class="report__meta">{{ r.school_year }}</span>
            </div>
            <div
              class="report__content markdown-body"
              :class="{ 'report__content--expanded': expanded.has(r.week_number) }"
              v-html="renderMd(r.content)"
            ></div>
            <span class="report__toggle">
              {{ expanded.has(r.week_number) ? 'Méně' : 'Více' }}
            </span>
          </div>
        </div>
      </div>
    </div>
    <p v-else class="empty">Žádné reporty zatím nejsou k dispozici</p>
  </div>
</template>

<style scoped>
.search-bar {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}
.search-input {
  flex: 1;
  max-width: 24rem;
  padding: var(--space-sm) var(--space-lg);
}
.search-count {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
}

.timeline {
  display: flex;
  flex-direction: column;
}

.timeline__day {
  display: grid;
  grid-template-columns: 6rem 1fr;
  gap: var(--space-lg);
}

.timeline__date-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: var(--space-sm);
}

.timeline__date {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-secondary);
  white-space: nowrap;
}

.timeline__line {
  width: 2px;
  flex: 1;
  background: rgba(255, 255, 255, 0.08);
  margin-top: var(--space-sm);
  border-radius: 1px;
}

.timeline__messages {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding-bottom: var(--space-xl);
}

.report {
  cursor: pointer;
  transition: border-color var(--transition);
}
.report:hover { border-color: rgba(255, 255, 255, 0.12); }

.report__header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: var(--space-sm); }
.report__title { font-size: var(--font-size-base); font-weight: var(--font-weight-medium); }
.report__meta { color: var(--text-muted); font-size: var(--font-size-sm); flex-shrink: 0; margin-left: var(--space-sm); }

.report__content {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  line-height: 1.6;
  max-height: 6em;
  overflow: hidden;
}
.report__content--expanded { max-height: none; }

.report__content :deep(p) { margin: 0 0 0.5em; }
.report__content :deep(ul) { margin: 0.25em 0; padding-left: 1.5em; }
.report__content :deep(li) { margin: 0.15em 0; }
.report__content :deep(li > ol) { list-style-type: none; }
.report__content :deep(h2) { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); margin: 0.75em 0 0.25em; }
.report__content :deep(strong) { font-weight: 600; }

.report__toggle {
  display: inline-block;
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--accent);
  cursor: pointer;
}

.empty { color: var(--text-muted); font-size: var(--font-size-base); }

@media (max-width: 768px) {
  .timeline__day {
    grid-template-columns: 1fr;
    gap: var(--space-xs);
  }
  .timeline__date-col {
    flex-direction: row;
    gap: var(--space-sm);
  }
  .timeline__line {
    height: 2px;
    width: auto;
    flex: 1;
    margin-top: 0;
    align-self: center;
  }
}
</style>
