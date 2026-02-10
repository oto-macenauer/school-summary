<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useStudentStore } from '@/stores/student'
import { getTimetable, getConfig } from '@/api/client'
import GlassCard from '@/components/ui/GlassCard.vue'

const store = useStudentStore()
const timetable = ref<any>(null)
const extraSubjects = ref<any[]>([])
const loading = ref(false)

const dayNames: Record<string, string> = {
  '1': 'Po', '2': 'Út', '3': 'St', '4': 'Čt', '5': 'Pá',
}

async function load() {
  if (!store.current) return
  loading.value = true
  try {
    const [tt, cfg] = await Promise.all([
      getTimetable(store.current),
      getConfig(),
    ])
    timetable.value = tt
    const student = cfg?.config?.students?.find((s: any) => s.name === store.current)
    extraSubjects.value = student?.extra_subjects || []
  } finally {
    loading.value = false
  }
}

function timeToMinutes(t: string): number {
  const [h, m] = t.split(':').map(Number)
  return (h || 0) * 60 + (m || 0)
}

function getDayName(dateStr: string): string {
  const d = new Date(dateStr)
  const weekday = d.getDay()
  return dayNames[String(weekday)] || dateStr
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return `${d.getDate()}.${d.getMonth() + 1}.`
}

// Collect all unique time slots across the week
const timeSlots = computed(() => {
  if (!timetable.value?.days) return []
  const slots = new Map<string, { begin: string; end: string }>()
  for (const day of timetable.value.days) {
    if (!day.is_school_day) continue
    for (const l of day.lessons) {
      const key = l.begin_time
      if (!slots.has(key)) slots.set(key, { begin: l.begin_time, end: l.end_time })
    }
  }
  // Add extra subjects time slots
  for (const ex of extraSubjects.value) {
    if (ex.time && !slots.has(ex.time)) {
      slots.set(ex.time, { begin: ex.time, end: '' })
    }
  }
  return Array.from(slots.values()).sort((a, b) => timeToMinutes(a.begin) - timeToMinutes(b.begin))
})

const schoolDays = computed(() => {
  if (!timetable.value?.days) return []
  return timetable.value.days.filter((d: any) => d.is_school_day)
})

function getLessonAt(day: any, time: string): any | null {
  return day.lessons?.find((l: any) => l.begin_time === time) || null
}

function getExtraAt(dayDate: string, time: string): any | null {
  const d = new Date(dayDate)
  const weekday = d.getDay()
  const dayMap: Record<number, string> = { 1: 'po', 2: 'ut', 3: 'st', 4: 'ct', 5: 'pa' }
  const dayKey = dayMap[weekday]
  return extraSubjects.value.find(
    (e: any) => e.time === time && e.days?.includes(dayKey)
  ) || null
}

onMounted(load)
watch(() => store.current, load)
</script>

<template>
  <div>
    <h2 class="page-title">Rozvrh</h2>
    <GlassCard v-if="timetable">
      <div class="table-wrap">
        <table class="tt-table">
          <thead>
            <tr>
              <th class="tt-th tt-th--time"></th>
              <th v-for="day in schoolDays" :key="day.date" class="tt-th">
                <div class="tt-day-name">{{ getDayName(day.date) }}</div>
                <div class="tt-day-date">{{ formatDate(day.date) }}</div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="slot in timeSlots" :key="slot.begin" class="tt-row">
              <td class="tt-time">{{ slot.begin }}</td>
              <td v-for="day in schoolDays" :key="day.date" class="tt-cell">
                <template v-if="getLessonAt(day, slot.begin)">
                  <div class="tt-lesson" :class="{ 'tt-lesson--changed': getLessonAt(day, slot.begin).is_changed }">
                    <span class="tt-subject">{{ getLessonAt(day, slot.begin).name }}</span>
                    <span v-if="getLessonAt(day, slot.begin).room" class="tt-room">{{ getLessonAt(day, slot.begin).room }}</span>
                    <span v-if="getLessonAt(day, slot.begin).is_changed" class="tt-change">{{ getLessonAt(day, slot.begin).change_description || 'Změna' }}</span>
                  </div>
                </template>
                <template v-else-if="getExtraAt(day.date, slot.begin)">
                  <div class="tt-lesson tt-lesson--extra">
                    <span class="tt-subject">{{ getExtraAt(day.date, slot.begin).name }}</span>
                  </div>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </GlassCard>
  </div>
</template>

<style scoped>
.table-wrap { overflow-x: auto; }

.tt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-base);
}

.tt-th {
  padding: var(--space-sm) var(--space-md);
  text-align: center;
  border-bottom: 1px solid var(--glass-border);
  font-weight: var(--font-weight-semibold);
}
.tt-th--time { width: 3.5rem; }

.tt-day-name { font-size: var(--font-size-base); }
.tt-day-date { font-size: var(--font-size-xs); color: var(--text-muted); font-weight: var(--font-weight-normal); }

.tt-row:not(:last-child) .tt-time,
.tt-row:not(:last-child) .tt-cell {
  border-bottom: var(--border-subtle);
}

.tt-time {
  padding: var(--space-sm) var(--space-md);
  color: var(--text-muted);
  font-size: var(--font-size-sm);
  text-align: right;
  white-space: nowrap;
  vertical-align: top;
}

.tt-cell {
  padding: var(--space-sm) var(--space-md);
  vertical-align: top;
  min-width: 7rem;
}

.tt-lesson {
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-xs);
  background: rgba(255, 255, 255, 0.03);
}

.tt-lesson--changed {
  background: rgba(245, 158, 11, 0.08);
  border-left: 2px solid var(--warning);
}

.tt-lesson--extra {
  background: rgba(99, 102, 241, 0.08);
  border-left: 2px solid var(--accent);
}

.tt-subject { font-weight: var(--font-weight-medium); display: block; }
.tt-room { font-size: var(--font-size-xs); color: var(--text-secondary); display: block; }
.tt-change { font-size: var(--font-size-xs); color: var(--warning); display: block; }
</style>
