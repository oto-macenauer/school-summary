<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import { useStudentStore } from '@/stores/student'
import { getResources } from '@/api/client'
import type { ResourceItem, ResourceCategory, ResourceQuery } from '@/types'

const PAGE_SIZE = 30
// Upper bound on pages fetched while looking for an anchored item
const MAX_ANCHOR_PAGES = 20

const store = useStudentStore()
const route = useRoute()
const items = ref<ResourceItem[]>([])
const total = ref(0)
const hasMore = ref(false)
const counts = ref<Record<ResourceCategory | 'all', number>>({ all: 0, komens: 0, mail: 0, report: 0 })
const unreadCount = ref(0)
const loading = ref(false)
const loadingMore = ref(false)
const expanded = ref<Set<string>>(new Set())
const highlighted = ref<string | null>(null)
const search = ref('')
const debouncedSearch = ref('')
const activeCategory = ref<ResourceCategory | 'all'>('all')
const activeImportance = ref<string | null>(null)
const activeSubject = ref<string | null>(null)
const availableTags = ref<{ subjects: string[]; importance: string[] }>({ subjects: [], importance: [] })
const sentinel = ref<HTMLElement | null>(null)

// Bumped on every reset so responses for stale filters are dropped
let requestId = 0
let searchTimer: ReturnType<typeof setTimeout> | undefined
let highlightTimer: ReturnType<typeof setTimeout> | undefined
let observer: IntersectionObserver | null = null
// Set by init(): scroll to the URL hash once the first page is in
let anchorPending = false

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

const tagLabels: Record<string, string> = {
  test: 'Test',
  homework: 'Úkol',
  trip: 'Výlet',
  event: 'Akce',
  absence: 'Absence',
  schedule_change: 'Změna rozvrhu',
  important: 'Důležité',
  info: 'Info',
}

function tagLabel(tag: string): string {
  return tagLabels[tag] || tag
}

function query(offset: number): ResourceQuery {
  return {
    offset,
    limit: PAGE_SIZE,
    category: activeCategory.value === 'all' ? undefined : activeCategory.value,
    importance: activeImportance.value ?? undefined,
    subject: activeSubject.value ?? undefined,
    q: debouncedSearch.value.trim() || undefined,
  }
}

async function load() {
  if (!store.current) return
  const id = ++requestId
  loading.value = true
  loadingMore.value = false

  try {
    const result = await getResources(store.current, query(0))
    if (id !== requestId) return
    items.value = result.items
    total.value = result.total
    hasMore.value = result.has_more
    counts.value = result.counts
    unreadCount.value = result.unread_count
    availableTags.value = result.available_tags
  } catch {
    if (id !== requestId) return
    items.value = []
    total.value = 0
    hasMore.value = false
  }

  loading.value = false
  await nextTick()
  rearmObserver()
  if (anchorPending) {
    anchorPending = false
    await focusAnchor()
  }
}

async function loadMore() {
  if (!store.current || loading.value || loadingMore.value || !hasMore.value) return
  const id = requestId
  loadingMore.value = true

  try {
    const result = await getResources(store.current, query(items.value.length))
    if (id !== requestId) return
    const seen = new Set(items.value.map(i => i.id))
    items.value = items.value.concat(result.items.filter(i => !seen.has(i.id)))
    total.value = result.total
    hasMore.value = result.has_more
  } catch {
    if (id !== requestId) return
    hasMore.value = false
  } finally {
    if (id === requestId) loadingMore.value = false
  }

  await nextTick()
  rearmObserver()
}

// Re-observing fires the callback again if the sentinel is still on screen,
// so a short page on a tall viewport keeps loading until it fills.
function rearmObserver() {
  if (!observer || !sentinel.value) return
  observer.unobserve(sentinel.value)
  observer.observe(sentinel.value)
}

async function focusAnchor() {
  const id = decodeURIComponent(route.hash.replace(/^#/, ''))
  if (!id) return

  let pages = 0
  while (!items.value.some(i => i.id === id) && hasMore.value && pages < MAX_ANCHOR_PAGES) {
    await loadMore()
    pages++
  }
  if (!items.value.some(i => i.id === id)) return

  expanded.value.add(id)
  highlighted.value = id
  await nextTick()
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  clearTimeout(highlightTimer)
  highlightTimer = setTimeout(() => { highlighted.value = null }, 2500)
}

function resetFilters() {
  clearTimeout(searchTimer)
  search.value = ''
  debouncedSearch.value = ''
  activeCategory.value = 'all'
  activeImportance.value = null
  activeSubject.value = null
}

async function init() {
  anchorPending = true
  resetFilters()
  expanded.value = new Set()
  // Resetting filters that were set triggers the filter watcher's load
  await nextTick()
  if (!loading.value) await load()
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

function categoryCount(key: ResourceCategory | 'all'): number {
  return counts.value[key] ?? 0
}

const filtersActive = computed(() =>
  activeCategory.value !== 'all' || !!activeImportance.value || !!activeSubject.value || !!debouncedSearch.value.trim(),
)

interface DayGroup {
  label: string
  items: ResourceItem[]
}

const groupedByDay = computed<DayGroup[]>(() => {
  const groups: Record<string, { ts: number; label: string; items: ResourceItem[] }> = {}
  for (const item of items.value) {
    const d = item.date ? new Date(item.date) : null
    const label = d ? d.toLocaleDateString('cs') : 'Bez data'
    if (!groups[label]) groups[label] = { ts: d ? d.getTime() : 0, label, items: [] }
    groups[label].items.push(item)
  }
  return Object.values(groups)
    .sort((a, b) => b.ts - a.ts)
    .map(({ label, items }) => ({ label, items }))
})

watch(search, value => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { debouncedSearch.value = value }, 300)
})
watch([activeCategory, activeImportance, activeSubject, debouncedSearch], () => { load() })
watch(() => store.current, init)
watch(() => route.hash, focusAnchor)

onMounted(() => {
  observer = new IntersectionObserver(
    entries => { if (entries.some(e => e.isIntersecting)) loadMore() },
    { rootMargin: '400px 0px' },
  )
  if (sentinel.value) observer.observe(sentinel.value)
  init()
})

onBeforeUnmount(() => {
  observer?.disconnect()
  clearTimeout(searchTimer)
  clearTimeout(highlightTimer)
})
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
      <div v-if="availableTags.importance.length" class="pills">
        <button
          v-for="tag in availableTags.importance"
          :key="tag"
          class="pill glass-btn"
          :class="{ 'pill--active': activeImportance === tag }"
          @click="activeImportance = activeImportance === tag ? null : tag"
        >
          {{ tagLabel(tag) }}
        </button>
      </div>
      <div v-if="availableTags.subjects.length" class="pills">
        <button
          v-for="subj in availableTags.subjects"
          :key="subj"
          class="pill glass-btn pill--subject"
          :class="{ 'pill--active': activeSubject === subj }"
          @click="activeSubject = activeSubject === subj ? null : subj"
        >
          {{ subj }}
        </button>
      </div>
      <div class="search-bar">
        <input
          v-model="search"
          type="text"
          class="search-input glass-btn"
          placeholder="Hledat..."
        />
        <span v-if="filtersActive" class="search-count">{{ total }} výsledků</span>
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
            :id="item.id"
            :key="item.id"
            class="item inner-card"
            :class="{ 'item--unread': item.isRead === false, 'item--highlight': highlighted === item.id }"
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
            <div v-if="item.tags && (item.tags.importance.length || item.tags.subjects.length || item.tags.temporal.length)" class="item__tags">
              <span
                v-for="imp in item.tags.importance"
                :key="imp"
                class="tag-pill"
                :class="`tag-pill--${imp}`"
                @click.stop="activeImportance = activeImportance === imp ? null : imp"
              >
                {{ tagLabel(imp) }}
              </span>
              <span
                v-for="subj in item.tags.subjects"
                :key="subj"
                class="tag-pill tag-pill--subject"
                @click.stop="activeSubject = activeSubject === subj ? null : subj"
              >
                {{ subj }}
              </span>
              <span
                v-for="temp in item.tags.temporal"
                :key="temp.from"
                class="tag-pill tag-pill--temporal"
              >
                {{ temp.label || temp.from }}
              </span>
            </div>
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

    <div ref="sentinel" class="sentinel" aria-hidden="true"></div>
    <p v-if="loadingMore" class="empty load-more">Načítání dalších...</p>
    <p v-else-if="!hasMore && items.length > PAGE_SIZE" class="empty load-more">Všech {{ total }} zobrazeno</p>
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
  max-width: 100%;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  max-width: 100%;
  padding: var(--space-xs) var(--space-md);
  border-radius: 999px;
  font-size: var(--font-size-sm);
  cursor: pointer;
  overflow-wrap: anywhere;
  transition: background var(--transition), border-color var(--transition), color var(--transition);
}
.pill--active {
  background: var(--accent-strong);
  color: #fff;
  border-color: var(--accent-strong);
}
.pill--active:hover { background: #4338ca; border-color: #4338ca; }
.pill__count {
  font-size: var(--font-size-xs);
  color: inherit;
}

.search-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-md);
  max-width: 100%;
}
.search-input {
  flex: 1 1 12rem;
  min-width: 0;
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
  max-width: 100%;
}

.timeline__day {
  display: grid;
  grid-template-columns: 6rem minmax(0, 1fr);
  gap: var(--space-lg);
  max-width: 100%;
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
  min-width: 0;
}

.item {
  cursor: pointer;
  transition: border-color var(--transition);
  overflow: hidden;
  min-width: 0;
}
.item:hover { border-color: rgba(255, 255, 255, 0.12); }
.item--unread { border-left: 2px solid var(--accent); }
.item--highlight {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.item { scroll-margin-top: 5rem; }

.item__header { display: flex; align-items: baseline; gap: var(--space-sm); min-width: 0; max-width: 100%; }
.item__tag {
  font-size: var(--font-size-xs);
  padding: 1px var(--space-xs);
  border-radius: 4px;
  flex-shrink: 0;
  font-weight: var(--font-weight-medium);
}
.item__tag--komens { background: var(--accent-soft); color: var(--accent-text); }
.item__tag--mail { background: rgba(52, 211, 153, 0.2); color: var(--success-text); }
.item__tag--report { background: rgba(251, 191, 36, 0.2); color: var(--warning-text); }

.item__title { font-size: var(--font-size-base); font-weight: var(--font-weight-medium); flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item__title--unread { font-weight: var(--font-weight-semibold); }
.item__time { color: var(--text-muted); font-size: var(--font-size-sm); flex-shrink: 0; }
.item__sender { color: var(--text-secondary); font-size: var(--font-size-sm); margin: var(--space-xs) 0 var(--space-sm); overflow-wrap: anywhere; }

.item__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  margin: var(--space-xs) 0;
  max-width: 100%;
}

.tag-pill {
  font-size: var(--font-size-xs);
  max-width: 100%;
  padding: 1px var(--space-sm);
  border-radius: 999px;
  cursor: pointer;
  overflow-wrap: anywhere;
}
.tag-pill--test { background: rgba(239, 68, 68, 0.22); color: var(--error-text); }
.tag-pill--homework { background: rgba(245, 158, 11, 0.22); color: var(--warning-text); }
.tag-pill--trip, .tag-pill--event { background: var(--accent-soft); color: var(--accent-text); }
.tag-pill--important { background: rgba(239, 68, 68, 0.25); color: var(--error-text); font-weight: var(--font-weight-semibold); }
.tag-pill--info { background: rgba(255, 255, 255, 0.12); color: var(--text-secondary); }
.tag-pill--absence, .tag-pill--schedule_change { background: rgba(245, 158, 11, 0.18); color: var(--warning-text); }
.tag-pill--subject { background: rgba(34, 197, 94, 0.2); color: var(--success-text); }
.tag-pill--temporal { background: rgba(99, 102, 241, 0.14); color: var(--accent-text); cursor: default; font-size: var(--font-size-xs); }

.item__body {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  line-height: 1.5;
  white-space: pre-line;
  max-height: 4.5em;
  max-width: 100%;
  min-width: 0;
  overflow: hidden;
  /* Message bodies are remote content: force-break anything unbreakable */
  overflow-wrap: anywhere;
  word-break: break-word;
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
  color: var(--accent-text);
  cursor: pointer;
}

.empty { color: var(--text-muted); font-size: var(--font-size-base); }
.sentinel { height: 1px; }
.load-more { text-align: center; padding: var(--space-md) 0; }

@media (max-width: 768px) {
  .timeline__day {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-xs);
  }
  .timeline__date-col {
    flex-direction: row;
    gap: var(--space-sm);
    align-items: center;
    padding-top: var(--space-md);
  }
  .timeline__line {
    height: 2px;
    width: auto;
    flex: 1;
    margin-top: 0;
    align-self: center;
  }
  .search-input { max-width: 100%; }
  .item__header { flex-wrap: wrap; }
  .item__title { flex: 1 1 100%; order: 2; white-space: normal; overflow: visible; }
  .item__time { order: 1; }
  .item__toggle { padding: var(--space-xs) 0; }
}
</style>
