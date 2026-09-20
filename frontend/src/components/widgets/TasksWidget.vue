<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useStudentStore } from '@/stores/student'
import { setAgendaItemState } from '@/api/client'
import type { AgendaTask, AgendaTaskCounts, AgendaTaskKind } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'
import { plural } from '@/utils/czech'

const props = defineProps<{
  data: AgendaTask[] | null
  counts?: AgendaTaskCounts | null
}>()

const store = useStudentStore()

const kindLabels: Record<AgendaTaskKind, string> = {
  pay: 'Zaplatit',
  bring: 'Přinést',
  prepare: 'Připravit',
  buy: 'Koupit',
  sign: 'Podepsat',
  return: 'Vrátit',
  other: 'Úkol',
}

// Local copy so ticking a box does not need a dashboard reload.
const tasks = ref<AgendaTask[]>([...(props.data || [])])
watch(() => props.data, value => { tasks.value = [...(value || [])] })

const today = new Date().toISOString().slice(0, 10)

function dueLabel(due: string | null): string {
  if (!due) return ''
  const diff = Math.round(
    (new Date(`${due}T12:00:00`).getTime() - new Date(`${today}T12:00:00`).getTime()) / 86400000,
  )
  if (diff === 0) return 'dnes'
  if (diff === 1) return 'zítra'
  if (diff < 0) return 'po termínu'
  const d = new Date(`${due}T12:00:00`)
  return `${d.getDate()}. ${d.getMonth() + 1}.`
}

function isOverdue(due: string | null): boolean {
  return !!due && due < today
}

async function toggle(task: AgendaTask) {
  if (!store.current) return
  const next = !task.done
  task.done = next
  try {
    await setAgendaItemState(store.current, task.id, { done: next })
  } catch {
    task.done = !next
  }
}

const openCount = computed(() => props.counts?.open ?? tasks.value.filter(t => !t.done).length)
</script>

<template>
  <GlassCard title="Úkoly">
    <div class="tasks-header">
      <span v-if="openCount" class="badge badge--accent">
        {{ openCount }} {{ plural(openCount, 'otevřený', 'otevřené', 'otevřených') }}
      </span>
      <span v-if="counts?.overdue" class="badge badge--error">{{ counts.overdue }} po termínu</span>
    </div>
    <div v-if="tasks.length" class="tasks">
      <div v-for="task in tasks" :key="task.id" class="task" :class="{ 'task--done': task.done }">
        <label class="task__check">
          <input type="checkbox" :checked="task.done" @change="toggle(task)" />
          <span class="visually-hidden">Hotovo</span>
        </label>
        <span class="task__title">{{ task.title }}</span>
        <span
          v-if="task.due"
          class="task__due"
          :class="{ 'task__due--overdue': isOverdue(task.due) }"
        >{{ dueLabel(task.due) }}</span>
        <span class="task__kind">{{ kindLabels[task.kind] }}</span>
      </div>
      <RouterLink
        :to="{ name: 'checklist', params: { student: store.current?.toLowerCase() } }"
        class="tasks__more"
      >Všechny úkoly</RouterLink>
    </div>
    <p v-else class="empty">Nic k vyřízení</p>
  </GlassCard>
</template>

<style scoped>
.tasks-header {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  margin-bottom: var(--space-sm);
}
.tasks-header:empty { display: none; }

.tasks { display: flex; flex-direction: column; max-width: 100%; }

.task {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xs) 0;
  border-bottom: var(--border-subtle);
  font-size: var(--font-size-base);
  min-width: 0;
}
.task:last-of-type { border-bottom: none; }
.task--done .task__title { text-decoration: line-through; color: var(--text-muted); }

.task__check {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 26px;
  height: 26px;
  cursor: pointer;
}
.task__check input {
  width: 17px;
  height: 17px;
  accent-color: var(--accent-strong);
  cursor: pointer;
}

.task__title {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task__due {
  flex: 0 0 auto;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  white-space: nowrap;
}
.task__due--overdue { color: var(--error-text); }
.task__kind {
  flex: 0 0 auto;
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  white-space: nowrap;
}

.tasks__more {
  margin-top: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--accent-text);
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.empty { color: var(--text-muted); font-size: var(--font-size-base); }

@media (max-width: 480px) {
  .task__kind { display: none; }
}
</style>
