<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { marked } from 'marked'
import { useStudentStore } from '@/stores/student'
import { getKomens, getMail, getGDriveReports } from '@/api/client'
import type { ResourceItem, ResourceCategory } from '@/types'

const store = useStudentStore()
const items = ref<ResourceItem[]>([])
const loading = ref(false)
const expanded = ref<Set<string>>(new Set())
const search = ref('')
const activeCategory = ref<ResourceCategory | 'all'>('all')

const categories: { key: ResourceCategory | 'all'; label: string }[] = [
  { key: 'all', label: 'Vše' },
  { key: 'komens', label: 'Komens' },
  { key: 'mail', label: 'Mail' },
  { key: 'report', label: 'Reporty' },
]

const categoryLabels: Record<ResourceCategory, string> = {
  komens: 'Komens',
  mail: 'Mail',
  report: 'Report',
}

function weekStartDate(weekNumber: number, schoolYear: string): string {
  // school_year is "2025/2026" — extract start year, derive Sep 1
  const startYear = parseInt(schoolYear.split('/')[0], 10)
  if (isNaN(startYear)) return new Date().toISOString()
  const sep1 = new Date(startYear, 8, 1) // months are 0-indexed
  // Monday of the week containing Sep 1 (same logic as backend)
  const day = sep1.getDay()
  const mondayOffset = day === 0 ? -6 : 1 - day
  const startMonday = new Date(sep1)
  startMonday.setDate(sep1.getDate() + mondayOffset)
  // Week N starts at startMonday + (N-1)*7
  const weekStart = new Date(startMonday)
  weekStart.setDate(startMonday.getDate() + (weekNumber - 1) * 7)
  return weekStart.toISOString()
}

async function load() {
  if (!store.current) return
  loading.value = true
  const all: ResourceItem[] = []

  const [komensResult, mailResult, reportsResult] = await Promise.allSettled([
    getKomens(store.current),
    getMail(store.current),
    getGDriveReports(store.current),
  ])

  if (komensResult.status === 'fulfilled' && komensResult.value?.recent_messages) {
    for (const m of komensResult.value.recent_messages) {
      all.push({
        id: `komens-${m.id}`,
        category: 'komens',
        title: m.title,
        sender: m.sender,
        date: m.date,
        body: m.text,
        isRead: m.is_read,
      })
    }
  }

  if (mailResult.status === 'fulfilled' && mailResult.value?.messages) {
    for (const m of mailResult.value.messages) {
      all.push({
        id: `mail-${m.id}`,
        category: 'mail',
        title: m.subject,
        sender: m.sender,
        date: m.date,
        body: m.body,
      })
    }
  }

  if (reportsResult.status === 'fulfilled' && reportsResult.value?.reports) {
    for (const r of reportsResult.value.reports) {
      all.push({
        id: `report-${r.week_number}`,
        category: 'report',
        title: r.source_file,
        sender: r.school_year,
        date: weekStartDate(r.week_number, r.school_year),
        body: r.content,
        isMarkdown: true,
      })
    }
  }

  items.value = all
  loading.value = false
}

function toggle(id: string) {
  if (expanded.value.has(id)) {
    expanded.value.delete(id)
  } else {
    expanded.value.add(id)
  }
}

function renderMd(text: string): string {
  return marked.parse(text) as string
}

const filtered = computed(() => {
  let list = items.value
  if (activeCategory.value !== 'all') {
    list = list.filter(i => i.category === activeCategory.value)
  }
  const q = search.value.toLowerCase().trim()
  if (q) {
    list = list.filter(i =>
      (i.title?.toLowerCase().includes(q)) ||
      (i.sender?.toLowerCase().includes(q)) ||
      (i.body?.toLowerCase().includes(q))
    )
  }
  return list
})

function categoryCount(key: ResourceCategory | 'all'): number {
  if (key === 'all') return items.value.length
  return items.value.filter(i => i.category === key).length
}

const unreadCount = computed(() => items.value.filter(i => i.category === 'komens' && i.isRead === false).length)

interface DayGroup {
  label: string
  items: ResourceItem[]
}

const groupedByDay = computed<DayGroup[]>(() => {
  const groups: Record<string, { ts: number; label: string; items: ResourceItem[] }> = {}
  for (const item of filtered.value) {
    const d = item.date ? new Date(item.date) : null
    const label = d ? d.toLocaleDateString('cs') : 'Bez data'
    if (!groups[label]) groups[label] = { ts: d ? d.getTime() : 0, label, items: [] }
    groups[label].items.push(item)
  }
  return Object.values(groups)
    .sort((a, b) => b.ts - a.ts)
    .map(({ label, items }) => ({ label, items }))
})

onMounted(load)
watch(() => store.current, load)
</script>

<template>
  <div>
    <h2 class="page-title">
      Zprávy
      <span v-if="unreadCount" class="badge badge--accent" style="margin-left: var(--space-sm);">
        {{ unreadCount }} nepřečtených
      </span>
    </h2>

    <div class="filters">
      <div class="pills">
        <button
          v-for="cat in categories"
          :key="cat.key"
          class="pill glass-btn"
          :class="{ 'pill--active': activeCategory === cat.key }"
          @click="activeCategory = cat.key"
        >
          {{ cat.label }}
          <span class="pill__count">{{ categoryCount(cat.key) }}</span>
        </button>
      </div>
      <div class="search-bar">
        <input
          v-model="search"
          type="text"
          class="search-input glass-btn"
          placeholder="Hledat..."
        />
        <span v-if="search" class="search-count">{{ filtered.length }} výsledků</span>
      </div>
    </div>

    <div v-if="loading && !items.length" class="empty">Načítání...</div>

    <div v-else-if="groupedByDay.length" class="timeline">
      <div v-for="group in groupedByDay" :key="group.label" class="timeline__day">
        <div class="timeline__date-col">
          <span class="timeline__date">{{ group.label }}</span>
          <div class="timeline__line"></div>
        </div>
        <div class="timeline__items">
          <div
            v-for="item in group.items"
            :key="item.id"
            class="item inner-card"
            :class="{ 'item--unread': item.isRead === false }"
            @click="toggle(item.id)"
          >
            <div class="item__header">
              <span class="item__tag" :class="`item__tag--${item.category}`">{{ categoryLabels[item.category] }}</span>
              <strong class="item__title" :class="{ 'item__title--unread': item.isRead === false }">{{ item.title }}</strong>
              <span class="item__time">
                {{ item.date ? new Date(item.date).toLocaleTimeString('cs', { hour: '2-digit', minute: '2-digit' }) : '' }}
              </span>
            </div>
            <div v-if="item.sender" class="item__sender">{{ item.sender }}</div>
            <div
              v-if="item.isMarkdown"
              class="item__body markdown-body"
              :class="{ 'item__body--expanded': expanded.has(item.id) }"
              v-html="renderMd(item.body)"
            ></div>
            <p
              v-else
              class="item__body"
              :class="{ 'item__body--expanded': expanded.has(item.id) }"
            >{{ item.body }}</p>
            <span v-if="item.body?.length > 200" class="item__toggle">
              {{ expanded.has(item.id) ? 'Méně' : 'Více' }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <p v-else-if="!loading" class="empty">Žádné zdroje k zobrazení</p>
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.pills {
  display: flex;
  gap: var(--space-xs);
  flex-wrap: wrap;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-xs) var(--space-md);
  border-radius: 999px;
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--transition);
}
.pill--active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.pill__count {
  font-size: var(--font-size-xs);
  opacity: 0.7;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: var(--space-md);
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

.timeline__items {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding-bottom: var(--space-xl);
}

.item {
  cursor: pointer;
  transition: border-color var(--transition);
}
.item:hover { border-color: rgba(255, 255, 255, 0.12); }
.item--unread { border-left: 2px solid var(--accent); }

.item__header { display: flex; align-items: baseline; gap: var(--space-sm); }
.item__tag {
  font-size: var(--font-size-xs);
  padding: 1px var(--space-xs);
  border-radius: 4px;
  flex-shrink: 0;
  font-weight: var(--font-weight-medium);
}
.item__tag--komens { background: rgba(99, 102, 241, 0.2); color: rgb(165, 167, 252); }
.item__tag--mail { background: rgba(52, 211, 153, 0.2); color: rgb(110, 231, 183); }
.item__tag--report { background: rgba(251, 191, 36, 0.2); color: rgb(252, 211, 77); }

.item__title { font-size: var(--font-size-base); font-weight: var(--font-weight-medium); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item__title--unread { font-weight: var(--font-weight-semibold); }
.item__time { color: var(--text-muted); font-size: var(--font-size-sm); flex-shrink: 0; }
.item__sender { color: var(--text-secondary); font-size: var(--font-size-sm); margin: var(--space-xs) 0 var(--space-sm); }

.item__body {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  line-height: 1.5;
  white-space: pre-line;
  max-height: 4.5em;
  overflow: hidden;
}
.item__body--expanded { max-height: none; }

.item__body.markdown-body { white-space: normal; line-height: 1.6; max-height: 6em; }
.item__body.markdown-body.item__body--expanded { max-height: none; }
.item__body :deep(p) { margin: 0 0 0.5em; }
.item__body :deep(ul) { margin: 0.25em 0; padding-left: 1.5em; }
.item__body :deep(li) { margin: 0.15em 0; }
.item__body :deep(li > ol) { list-style-type: none; }
.item__body :deep(h2) { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); margin: 0.75em 0 0.25em; }
.item__body :deep(strong) { font-weight: 600; }

.item__toggle {
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
