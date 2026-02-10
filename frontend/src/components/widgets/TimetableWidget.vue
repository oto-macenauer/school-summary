<script setup lang="ts">
import { computed } from 'vue'
import type { TimetableDay } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'

interface ExtraSubject {
  name: string
  time: string
  days: string[]
}

const props = defineProps<{
  data: TimetableDay | null
  extraSubjects?: ExtraSubject[]
}>()

interface GroupedLesson {
  begin_time: string
  end_time: string
  name: string
  room: string | null
  is_changed: boolean
  change_description: string | null
  is_extra: boolean
}

const dayMap: Record<number, string> = { 1: 'po', 2: 'ut', 3: 'st', 4: 'ct', 5: 'pa' }

function timeToMinutes(t: string): number {
  const [h, m] = t.split(':').map(Number)
  return (h || 0) * 60 + (m || 0)
}

const groupedLessons = computed<GroupedLesson[]>(() => {
  const groups: GroupedLesson[] = []

  if (props.data?.lessons) {
    for (const l of props.data.lessons) {
      const last = groups[groups.length - 1]
      if (last && last.begin_time === l.begin_time && last.name === l.name) {
        last.end_time = l.end_time
      } else {
        groups.push({
          begin_time: l.begin_time,
          end_time: l.end_time,
          name: l.name,
          room: l.room,
          is_changed: l.is_changed,
          change_description: l.change_description,
          is_extra: false,
        })
      }
    }
  }

  // Merge today's extra subjects
  if (props.extraSubjects?.length) {
    const todayKey = dayMap[new Date().getDay()]
    for (const ex of props.extraSubjects) {
      if (todayKey && ex.days?.includes(todayKey)) {
        groups.push({
          begin_time: ex.time,
          end_time: '',
          name: ex.name,
          room: null,
          is_changed: false,
          change_description: null,
          is_extra: true,
        })
      }
    }
  }

  groups.sort((a, b) => timeToMinutes(a.begin_time) - timeToMinutes(b.begin_time))
  return groups
})
</script>

<template>
  <GlassCard title="Rozvrh dnes">
    <div v-if="data && data.is_school_day" class="lessons">
      <div
        v-for="(l, i) in groupedLessons"
        :key="i"
        class="lesson"
        :class="{ 'lesson--changed': l.is_changed, 'lesson--extra': l.is_extra }"
      >
        <span class="lesson__time">{{ l.begin_time }}</span>
        <span class="lesson__name">{{ l.name }}</span>
        <span class="lesson__room">{{ l.room || '' }}</span>
        <span v-if="l.is_changed" class="badge badge--warning">{{ l.change_description || 'Změna' }}</span>
      </div>
    </div>
    <p v-else-if="data" class="empty">{{ data.description || 'Volno' }}</p>
    <p v-else class="empty">Rozvrh není k dispozici</p>
  </GlassCard>
</template>

<style scoped>
.lessons { display: flex; flex-direction: column; gap: var(--space-xs); }
.lesson {
  display: flex; align-items: center; gap: var(--space-sm);
  padding: var(--space-sm) 0;
  border-bottom: var(--border-subtle);
  font-size: var(--font-size-base);
}
.lesson:last-child { border-bottom: none; }
.lesson__time { color: var(--text-muted); font-size: var(--font-size-sm); min-width: 3.5rem; }
.lesson__name { font-weight: var(--font-weight-medium); flex: 1; }
.lesson__room { color: var(--text-secondary); font-size: var(--font-size-sm); }
.lesson--changed {
  background: rgba(245, 158, 11, 0.05);
  border-radius: var(--radius-xs);
  padding: var(--space-sm);
}
.lesson--extra .lesson__name { color: var(--accent); }
.lesson--extra .lesson__time { color: var(--accent); opacity: 0.7; }
.empty { color: var(--text-muted); font-size: var(--font-size-base); }
</style>
