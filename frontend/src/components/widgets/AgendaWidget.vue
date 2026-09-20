<script setup lang="ts">
import { computed } from 'vue'
import { useStudentStore } from '@/stores/student'
import type { AgendaEvent, AgendaEventKind } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'

const props = defineProps<{ data: AgendaEvent[] | null }>()
const store = useStudentStore()

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

const today = new Date().toISOString().slice(0, 10)

function dayDiff(date: string): number {
  const a = new Date(`${date}T12:00:00`).getTime()
  const b = new Date(`${today}T12:00:00`).getTime()
  return Math.round((a - b) / 86400000)
}

function whenLabel(event: AgendaEvent): string {
  const start = dayDiff(event.date_from)
  const end = event.date_to ? dayDiff(event.date_to) : start
  if (start === 0) return 'Dnes'
  // Started earlier and not over yet — a trip in progress, not something today
  if (start < 0 && end >= 0) return 'Probíhá'
  if (start === 1) return 'Zítra'
  const d = new Date(`${event.date_from}T12:00:00`)
  return `${d.getDate()}. ${d.getMonth() + 1}.`
}

const events = computed(() => props.data || [])
</script>

<template>
  <GlassCard title="Co nás čeká">
    <div v-if="events.length" class="events">
      <RouterLink
        v-for="event in events"
        :key="event.id"
        :to="{ name: 'calendar', params: { student: store.current?.toLowerCase() } }"
        class="event"
      >
        <span class="event__when">{{ whenLabel(event) }}</span>
        <span class="event__title">{{ event.title }}</span>
        <span class="event__kind" :class="`event__kind--${event.kind}`">
          {{ kindLabels[event.kind] }}
        </span>
      </RouterLink>
    </div>
    <p v-else class="empty">Nic naplánovaného</p>
  </GlassCard>
</template>

<style scoped>
.events { display: flex; flex-direction: column; max-width: 100%; }

.event {
  display: flex;
  align-items: baseline;
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
  border-bottom: var(--border-subtle);
  font-size: var(--font-size-base);
  color: inherit;
  text-decoration: none;
  min-width: 0;
}
.event:last-child { border-bottom: none; }
.event:hover { background: rgba(255, 255, 255, 0.05); text-decoration: none; }

.event__when {
  flex: 0 0 3.5rem;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  white-space: nowrap;
}
.event__title {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.event__kind {
  flex: 0 0 auto;
  padding: 1px var(--space-sm);
  border-radius: 999px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  background: rgba(255, 255, 255, 0.12);
  color: var(--text-secondary);
}
.event__kind--test,
.event__kind--exam { background: rgba(239, 68, 68, 0.22); color: var(--error-text); }
.event__kind--homework,
.event__kind--deadline { background: rgba(245, 158, 11, 0.22); color: var(--warning-text); }
.event__kind--trip,
.event__kind--event { background: var(--accent-soft); color: var(--accent-text); }
.event__kind--meeting,
.event__kind--holiday { background: rgba(52, 211, 153, 0.2); color: var(--success-text); }

.empty { color: var(--text-muted); font-size: var(--font-size-base); }

@media (max-width: 480px) {
  .event { flex-wrap: wrap; }
  .event__title { flex: 1 1 100%; white-space: normal; overflow-wrap: anywhere; }
}
</style>
