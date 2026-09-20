<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useStudentStore } from '@/stores/student'
import { getTimetable, getConfig } from '@/api/client'
import GlassCard from '@/components/ui/GlassCard.vue'

const store = useStudentStore()
const timetable = ref<any>(null)
const extraSubjects = ref<any[]>([])
const loading = ref(false)
const weekOffset = ref(0)

const dayNames: Record<string, string> = {
  '1': 'Po', '2': 'Út', '3': 'St', '4': 'Čt', '5': 'Pá',
}

const fullDayNames: Record<string, string> = {
  '1': 'Pondělí', '2': 'Úterý', '3': 'Středa', '4': 'Čtvrtek', '5': 'Pátek',
}

function mondayOf(offset: number): Date {
  const d = new Date()
  d.setHours(12, 0, 0, 0)
  // getDay(): Sunday = 0 — treat it as the end of the previous week
  const shift = (d.getDay() + 6) % 7
  d.setDate(d.getDate() - shift + offset * 7)
  return d
}

function toIsoDate(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

async function load() {
  if (!store.current) return
  loading.value = true
  try {
    const date = weekOffset.value === 0 ? undefined : toIsoDate(mondayOf(weekOffset.value))
    const [tt, cfg] = await Promise.all([
      getTimetable(store.current, date),
      getConfig(),
    ])
    timetable.value = tt
    const student = cfg?.config?.students?.find((s: any) => s.name === store.current)
    extraSubjects.value = student?.extra_subjects || []
  } finally {
    loading.value = false
  }
}

function shiftWeek(delta: number) {
  weekOffset.value += delta
}

const weekLabel = computed(() => {
  if (weekOffset.value === 0) return 'Tento týden'
  if (weekOffset.value === -1) return 'Minulý týden'
  if (weekOffset.value === 1) return 'Příští týden'
  const start = mondayOf(weekOffset.value)
  const end = new Date(start)
  end.setDate(end.getDate() + 4)
  return `${start.getDate()}.${start.getMonth() + 1}. – ${end.getDate()}.${end.getMonth() + 1}.`
})

function timeToMinutes(t: string): number {
  const [h, m] = t.split(':').map(Number)
  return (h || 0) * 60 + (m || 0)
}

function getDayName(dateStr: string): string {
  const d = new Date(dateStr)
  const weekday = d.getDay()
  return dayNames[String(weekday)] || dateStr
}

function getFullDayName(dateStr: string): string {
  const d = new Date(dateStr)
  return fullDayNames[String(d.getDay())] || dateStr
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

// Themes recorded by teachers — what was actually taught, per day
const noteDays = computed(() => {
  return schoolDays.value
    .map((day: any) => ({
      date: day.date,
      notes: (day.lessons || []).filter((l: any) => l.theme && l.theme.trim()),
    }))
    .filter((d: any) => d.notes.length > 0)
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
watch(weekOffset, load)
</script>

<template>
  <div>
    <div class="page-head">
      <h2 class="page-title">Rozvrh</h2>
      <div class="week-nav">
        <button class="glass-btn" :disabled="loading" @click="shiftWeek(-1)">‹</button>
        <button
          class="glass-btn week-label"
          :class="{ 'glass-btn--accent': weekOffset !== 0 }"
          :disabled="loading || weekOffset === 0"
          @click="weekOffset = 0"
        >{{ weekLabel }}</button>
        <button class="glass-btn" :disabled="loading" @click="shiftWeek(1)">›</button>
      </div>
    </div>

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
                    <span
                      v-if="getLessonAt(day, slot.begin).theme"
                      class="tt-theme"
                      :title="getLessonAt(day, slot.begin).theme"
                    >{{ getLessonAt(day, slot.begin).theme }}</span>
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

    <GlassCard v-if="noteDays.length" class="notes-card">
      <h3 class="notes-title">Probraná látka</h3>
      <div v-for="day in noteDays" :key="day.date" class="notes-day">
        <div class="notes-day-head">{{ getFullDayName(day.date) }} {{ formatDate(day.date) }}</div>
        <ul class="notes-list">
          <li v-for="(lesson, i) in day.notes" :key="i" class="notes-item">
            <span class="notes-subject">{{ lesson.abbrev || lesson.name }}</span>
            <span class="notes-text">{{ lesson.theme }}</span>
          </li>
        </ul>
      </div>
    </GlassCard>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  flex-wrap: wrap;
}

.week-nav {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  margin-bottom: var(--space-md);
}

.week-label { min-width: 7.5rem; }

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

.tt-theme {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-top: 2px;
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  overflow-wrap: anywhere;
}

.notes-card { margin-top: var(--space-md); }

.notes-title {
  margin: 0 0 var(--space-sm);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
}

.notes-day:not(:last-child) { margin-bottom: var(--space-md); }

.notes-day-head {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  margin-bottom: var(--space-xs);
}

.notes-list { list-style: none; margin: 0; padding: 0; }

.notes-item {
  display: flex;
  gap: var(--space-sm);
  padding: 2px 0;
  font-size: var(--font-size-sm);
  overflow-wrap: anywhere;
}

.notes-subject {
  flex: 0 0 3.5rem;
  color: var(--accent);
  font-weight: var(--font-weight-medium);
}

.notes-text { flex: 1; color: var(--text-secondary); }
</style>
