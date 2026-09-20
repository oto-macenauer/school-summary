<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useStudentStore } from '@/stores/student'
import { getAgendaTasks, setAgendaItemState } from '@/api/client'
import type { AgendaTask, AgendaTaskCounts, AgendaTaskKind } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'
import { plural, pluralize } from '@/utils/czech'

const store = useStudentStore()
const tasks = ref<AgendaTask[]>([])
const counts = ref<AgendaTaskCounts>({ open: 0, overdue: 0, due_soon: 0 })
const today = ref(new Date().toISOString().slice(0, 10))
const loading = ref(false)
const showDone = ref(false)

const kindLabels: Record<AgendaTaskKind, string> = {
  pay: 'Zaplatit',
  bring: 'Přinést',
  prepare: 'Připravit',
  buy: 'Koupit',
  sign: 'Podepsat',
  return: 'Vrátit',
  other: 'Úkol',
}

async function load() {
  if (!store.current) return
  loading.value = true
  try {
    const data = await getAgendaTasks(store.current)
    tasks.value = data.tasks
    counts.value = data.counts
    today.value = data.today
  } catch {
    tasks.value = []
  } finally {
    loading.value = false
  }
}

async function toggleDone(task: AgendaTask) {
  if (!store.current) return
  const next = !task.done
  task.done = next
  counts.value.open += next ? -1 : 1
  try {
    await setAgendaItemState(store.current, task.id, { done: next })
  } catch {
    task.done = !next
    counts.value.open += next ? 1 : -1
  }
}

async function dismiss(task: AgendaTask) {
  if (!store.current) return
  const previous = tasks.value
  tasks.value = tasks.value.filter(t => t.id !== task.id)
  if (!task.done) counts.value.open -= 1
  try {
    await setAgendaItemState(store.current, task.id, { dismissed: true })
  } catch {
    tasks.value = previous
    if (!task.done) counts.value.open += 1
  }
}

function dayDiff(due: string): number {
  const a = new Date(`${due}T12:00:00`).getTime()
  const b = new Date(`${today.value}T12:00:00`).getTime()
  return Math.round((a - b) / 86400000)
}

function dueLabel(due: string | null): string {
  if (!due) return 'Bez termínu'
  const diff = dayDiff(due)
  if (diff === 0) return 'Dnes'
  if (diff === 1) return 'Zítra'
  if (diff === -1) return 'Včera'
  const d = new Date(`${due}T12:00:00`)
  const formatted = `${d.getDate()}. ${d.getMonth() + 1}.`
  if (diff >= 0) return formatted
  return `${formatted} (${pluralize(-diff, 'den', 'dny', 'dní')} po termínu)`
}

function amountLabel(task: AgendaTask): string {
  if (task.amount === null) return ''
  const value = Number.isInteger(task.amount)
    ? task.amount.toLocaleString('cs')
    : task.amount.toFixed(2)
  return `${value} ${task.currency || 'CZK'}`
}

interface Section {
  key: string
  label: string
  tone: 'overdue' | 'soon' | 'later' | 'undated' | 'done'
  tasks: AgendaTask[]
}

/** Open tasks bucketed by urgency; finished ones collected at the bottom. */
const sections = computed<Section[]>(() => {
  const buckets: Record<string, AgendaTask[]> = {
    overdue: [], soon: [], later: [], undated: [], done: [],
  }
  for (const task of tasks.value) {
    if (task.done) {
      buckets.done.push(task)
    } else if (!task.due) {
      buckets.undated.push(task)
    } else {
      const diff = dayDiff(task.due)
      if (diff < 0) buckets.overdue.push(task)
      else if (diff <= 7) buckets.soon.push(task)
      else buckets.later.push(task)
    }
  }

  const defs: { key: string; label: string; tone: Section['tone'] }[] = [
    { key: 'overdue', label: 'Po termínu', tone: 'overdue' },
    { key: 'soon', label: 'Tento týden', tone: 'soon' },
    { key: 'later', label: 'Později', tone: 'later' },
    { key: 'undated', label: 'Bez termínu', tone: 'undated' },
  ]
  const result = defs
    .filter(def => buckets[def.key].length)
    .map(def => ({ ...def, tasks: buckets[def.key] }))

  if (showDone.value && buckets.done.length) {
    result.push({ key: 'done', label: 'Hotovo', tone: 'done', tasks: buckets.done })
  }
  return result
})

const doneCount = computed(() => tasks.value.filter(t => t.done).length)

onMounted(load)
watch(() => store.current, load)
</script>

<template>
  <div>
    <div class="page-head">
      <h2 class="page-title">
        Úkoly
        <span v-if="counts.open" class="page-title__sub">
          — {{ counts.open }} {{ plural(counts.open, 'otevřený', 'otevřené', 'otevřených') }}
        </span>
      </h2>
      <div class="head-actions">
        <span v-if="counts.overdue" class="badge badge--error">{{ counts.overdue }} po termínu</span>
        <button
          v-if="doneCount"
          class="glass-btn toggle-btn"
          @click="showDone = !showDone"
        >{{ showDone ? 'Skrýt hotové' : `Hotové (${doneCount})` }}</button>
      </div>
    </div>

    <LoadingSpinner v-if="loading && !tasks.length" />

    <div v-else-if="sections.length" class="sections">
      <GlassCard v-for="section in sections" :key="section.key" class="section">
        <h3 class="section__title" :class="`section__title--${section.tone}`">
          {{ section.label }}
          <span class="section__count">{{ section.tasks.length }}</span>
        </h3>
        <div class="tasks">
          <div
            v-for="task in section.tasks"
            :key="task.id"
            class="task"
            :class="{ 'task--done': task.done }"
          >
            <label class="task__check">
              <input type="checkbox" :checked="task.done" @change="toggleDone(task)" />
              <span class="visually-hidden">Hotovo</span>
            </label>
            <div class="task__body">
              <span class="task__title">{{ task.title }}</span>
              <div class="task__meta">
                <span class="task__kind" :class="`task__kind--${task.kind}`">
                  {{ kindLabels[task.kind] }}
                </span>
                <span v-if="task.amount !== null" class="task__amount">{{ amountLabel(task) }}</span>
                <span
                  class="task__due"
                  :class="{ 'task__due--overdue': section.tone === 'overdue' }"
                >{{ dueLabel(task.due) }}</span>
                <span v-if="task.subject" class="task__subject">{{ task.subject }}</span>
              </div>
              <p v-if="task.note" class="task__note">{{ task.note }}</p>
            </div>
            <button
              class="task__dismiss"
              title="Skrýt úkol"
              aria-label="Skrýt úkol"
              @click="dismiss(task)"
            >&times;</button>
          </div>
        </div>
      </GlassCard>
    </div>

    <p v-else-if="!loading" class="empty">
      Žádné úkoly. Vytáhnou se automaticky ze zpráv a e-mailů.
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
.head-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
}
.toggle-btn { min-height: 40px; }

.sections { display: flex; flex-direction: column; gap: var(--space-sm); }
.section { max-width: 100%; }

.section__title {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-secondary);
  margin-bottom: var(--space-md);
}
.section__title--overdue { color: var(--error-text); }
.section__title--soon { color: var(--warning-text); }
.section__count {
  padding: 0 var(--space-sm);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  color: var(--text-secondary);
  letter-spacing: 0;
}

.tasks { display: flex; flex-direction: column; }

.task {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
  border-bottom: var(--border-subtle);
  min-width: 0;
  max-width: 100%;
}
.task:last-child { border-bottom: none; }
.task--done .task__title { text-decoration: line-through; color: var(--text-muted); }

.task__check {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  cursor: pointer;
}
.task__check input {
  width: 18px;
  height: 18px;
  accent-color: var(--accent-strong);
  cursor: pointer;
}

.task__body { flex: 1 1 auto; min-width: 0; }
.task__title {
  font-size: var(--font-size-base);
  overflow-wrap: anywhere;
}

.task__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-xs) var(--space-sm);
  margin-top: 2px;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.task__kind {
  padding: 1px var(--space-sm);
  border-radius: 999px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  background: rgba(255, 255, 255, 0.12);
  color: var(--text-secondary);
}
.task__kind--pay { background: rgba(245, 158, 11, 0.22); color: var(--warning-text); }
.task__kind--buy { background: rgba(52, 211, 153, 0.2); color: var(--success-text); }
.task__kind--sign,
.task__kind--return { background: var(--accent-soft); color: var(--accent-text); }

.task__amount {
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.task__due--overdue { color: var(--error-text); }
.task__note {
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--text-muted);
  overflow-wrap: anywhere;
}

.task__dismiss {
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
.task__dismiss:hover { color: var(--text-primary); background: rgba(255, 255, 255, 0.08); }

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.empty { color: var(--text-muted); font-size: var(--font-size-base); }
</style>
