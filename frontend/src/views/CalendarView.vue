<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useStudentStore } from '@/stores/student'
import { getAgendaEvents, setAgendaItemState } from '@/api/client'
import type { AgendaEvent, AgendaEventKind } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'
import { pluralize } from '@/utils/czech'

const store = useStudentStore()
const events = ref<AgendaEvent[]>([])
const today = ref(new Date().toISOString().slice(0, 10))
const total = ref(0)
const loading = ref(false)
const showAll = ref(false)
const activeKind = ref<AgendaEventKind | null>(null)

const kindLabels: Record<AgendaEventKind, string> = {
  test: 'Písemka',
  exam: 'Zkouška',
  homework: 'Úkol',
  trip: 'Výlet',
  event: 'Akce',
  meeting: 'Schůzka',
  holiday: 'Volno',
  deadline: 'Termín',
}

const weekdays = ['Neděle', 'Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota']

async function load() {
  if (!store.current) return
  loading.value = true
  try {
    const data = await getAgendaEvents(store.current, { all_time: showAll.value })
    events.value = data.events
    today.value = data.today
    total.value = data.total
  } catch {
    events.value = []
  } finally {
    loading.value = false
  }
}

async function dismiss(event: AgendaEvent) {
  if (!store.current) return
  const previous = events.value
  events.value = events.value.filter(e => e.id !== event.id)
  try {
    await setAgendaItemState(store.current, event.id, { dismissed: true })
  } catch {
    events.value = previous
  }
}

const availableKinds = computed(() => {
  const kinds = new Set<AgendaEventKind>()
  for (const event of events.value) kinds.add(event.kind)
  return [...kinds].sort()
})

const filtered = computed(() =>
  activeKind.value ? events.value.filter(e => e.kind === activeKind.value) : events.value,
)

interface DayGroup {
  date: string
  label: string
  meta: string
  isPast: boolean
  isToday: boolean
  events: AgendaEvent[]
}

/** Agenda view: only days that actually hold something get a row. */
const groups = computed<DayGroup[]>(() => {
  const byDate = new Map<string, AgendaEvent[]>()
  for (const event of filtered.value) {
    const key = event.date_from
    const bucket = byDate.get(key)
    if (bucket) bucket.push(event)
    else byDate.set(key, [event])
  }

  return [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, items]) => {
      const d = new Date(`${date}T12:00:00`)
      const diff = dayDiff(date, today.value)
      let label = weekdays[d.getDay()]
      if (diff === 0) label = 'Dnes'
      else if (diff === 1) label = 'Zítra'
      else if (diff === -1) label = 'Včera'
      // A multi-day event that started earlier is still going, so its day
      // row is only "past" once everything on it has finished.
      const ended = items.every(e => dayDiff(e.date_to || e.date_from, today.value) < 0)
      return {
        date,
        label,
        meta: `${d.getDate()}. ${d.getMonth() + 1}.`,
        isPast: diff < 0 && ended,
        isToday: diff === 0,
        events: items,
      }
    })
})

const pastCount = computed(() => groups.value.filter(g => g.isPast).length)

function dayDiff(a: string, b: string): number {
  const dateA = new Date(`${a}T12:00:00`).getTime()
  const dateB = new Date(`${b}T12:00:00`).getTime()
  return Math.round((dateA - dateB) / 86400000)
}

function rangeLabel(event: AgendaEvent): string {
  if (!event.date_to || event.date_to === event.date_from) return ''
  const end = new Date(`${event.date_to}T12:00:00`)
  return `do ${end.getDate()}. ${end.getMonth() + 1}.`
}

onMounted(load)
watch(() => store.current, load)
watch(showAll, load)
</script>

<template>
  <div>
    <div class="page-head">
      <h2 class="page-title">
        Kalendář
        <span v-if="total" class="page-title__sub">
          — {{ pluralize(total, 'událost', 'události', 'událostí') }}
        </span>
      </h2>
      <button class="glass-btn range-btn" @click="showAll = !showAll">
        {{ showAll ? 'Jen aktuální' : 'Zobrazit vše' }}
      </button>
    </div>

    <div v-if="availableKinds.length > 1" class="pills">
      <button
        class="pill glass-btn"
        :class="{ 'pill--active': activeKind === null }"
        @click="activeKind = null"
      >Vše</button>
      <button
        v-for="kind in availableKinds"
        :key="kind"
        class="pill glass-btn"
        :class="{ 'pill--active': activeKind === kind }"
        @click="activeKind = activeKind === kind ? null : kind"
      >{{ kindLabels[kind] }}</button>
    </div>

    <LoadingSpinner v-if="loading && !events.length" />

    <GlassCard v-else-if="groups.length" class="agenda">
      <p v-if="pastCount" class="agenda__hint">
        Zahrnuje i uplynulé dny (zobrazené světleji).
      </p>
      <div
        v-for="group in groups"
        :key="group.date"
        class="day"
        :class="{ 'day--past': group.isPast, 'day--today': group.isToday }"
      >
        <div class="day__head">
          <span class="day__label">{{ group.label }}</span>
          <span class="day__meta">{{ group.meta }}</span>
        </div>
        <div class="day__items">
          <div v-for="event in group.events" :key="event.id" class="entry">
            <span class="entry__kind" :class="`entry__kind--${event.kind}`">
              {{ kindLabels[event.kind] }}
            </span>
            <div class="entry__body">
              <span class="entry__title">{{ event.title }}</span>
              <div class="entry__meta">
                <span v-if="event.time_from" class="entry__time">{{ event.time_from }}</span>
                <span v-if="rangeLabel(event)" class="entry__range">{{ rangeLabel(event) }}</span>
                <span v-if="event.subject" class="entry__subject">{{ event.subject }}</span>
                <span v-if="event.location" class="entry__location">{{ event.location }}</span>
              </div>
              <p v-if="event.note" class="entry__note">{{ event.note }}</p>
            </div>
            <button
              class="entry__dismiss"
              title="Skrýt událost"
              aria-label="Skrýt událost"
              @click="dismiss(event)"
            >&times;</button>
          </div>
        </div>
      </div>
    </GlassCard>

    <p v-else-if="!loading" class="empty">
      Žádné události. Vytáhnou se automaticky ze zpráv a e-mailů.
    </p>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-md);
  max-width: 100%;
}
.range-btn { margin-bottom: var(--space-lg); min-height: 40px; }

.pills {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  margin-bottom: var(--space-lg);
  max-width: 100%;
}
.pill {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: var(--space-xs) var(--space-md);
  border-radius: 999px;
  font-size: var(--font-size-sm);
  cursor: pointer;
  overflow-wrap: anywhere;
}
.pill--active {
  background: var(--accent-strong);
  border-color: var(--accent-strong);
  color: #fff;
}

.agenda { max-width: 100%; }
.agenda__hint {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  margin-bottom: var(--space-md);
}

.day {
  display: grid;
  grid-template-columns: 6.5rem minmax(0, 1fr);
  gap: var(--space-lg);
  padding: var(--space-md) 0;
  border-bottom: var(--border-subtle);
  max-width: 100%;
}
.day:last-child { border-bottom: none; }
.day--past { opacity: 0.65; }
.day--today .day__label { color: var(--accent-text); }

.day__head {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.day__label {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  overflow-wrap: anywhere;
}
.day__meta { font-size: var(--font-size-sm); color: var(--text-secondary); }

.day__items {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  min-width: 0;
}

.entry {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  min-width: 0;
  max-width: 100%;
}

.entry__kind {
  flex: 0 0 auto;
  padding: 1px var(--space-sm);
  border-radius: 999px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  background: rgba(255, 255, 255, 0.12);
  color: var(--text-secondary);
}
.entry__kind--test,
.entry__kind--exam { background: rgba(239, 68, 68, 0.22); color: var(--error-text); }
.entry__kind--homework,
.entry__kind--deadline { background: rgba(245, 158, 11, 0.22); color: var(--warning-text); }
.entry__kind--trip,
.entry__kind--event { background: var(--accent-soft); color: var(--accent-text); }
.entry__kind--meeting { background: rgba(52, 211, 153, 0.2); color: var(--success-text); }
.entry__kind--holiday { background: rgba(34, 197, 94, 0.2); color: var(--success-text); }

.entry__body { flex: 1 1 auto; min-width: 0; }
.entry__title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  overflow-wrap: anywhere;
}

.entry__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs) var(--space-sm);
  margin-top: 2px;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}
.entry__time { color: var(--text-primary); font-variant-numeric: tabular-nums; }
.entry__note {
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  overflow-wrap: anywhere;
}

.entry__dismiss {
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-xs);
  background: none;
  color: var(--text-muted);
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
}
.entry__dismiss:hover { color: var(--text-primary); background: rgba(255, 255, 255, 0.08); }

.empty { color: var(--text-muted); font-size: var(--font-size-base); }

@media (max-width: 768px) {
  .day {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-xs);
  }
  .day__head {
    flex-direction: row;
    align-items: baseline;
    gap: var(--space-sm);
  }
  .range-btn { margin-bottom: var(--space-md); }
}
</style>
