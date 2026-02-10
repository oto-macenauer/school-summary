<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useStudentStore } from '@/stores/student'
import { getKomens } from '@/api/client'

const store = useStudentStore()
const komens = ref<any>(null)
const expanded = ref<Set<string>>(new Set())
const search = ref('')

async function load() {
  if (!store.current) return
  komens.value = await getKomens(store.current)
}

function toggle(id: string) {
  if (expanded.value.has(id)) {
    expanded.value.delete(id)
  } else {
    expanded.value.add(id)
  }
}

interface DayGroup {
  label: string
  messages: any[]
}

const filteredMessages = computed(() => {
  if (!komens.value?.recent_messages) return []
  const q = search.value.toLowerCase().trim()
  if (!q) return komens.value.recent_messages
  return komens.value.recent_messages.filter((m: any) =>
    (m.title?.toLowerCase().includes(q)) ||
    (m.sender?.toLowerCase().includes(q)) ||
    (m.text?.toLowerCase().includes(q))
  )
})

const groupedByDay = computed<DayGroup[]>(() => {
  const map = new Map<string, any[]>()
  for (const m of filteredMessages.value) {
    const key = m.date ? new Date(m.date).toLocaleDateString('cs') : 'Bez data'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(m)
  }
  return Array.from(map.entries()).map(([label, messages]) => ({ label, messages }))
})

onMounted(load)
watch(() => store.current, load)
</script>

<template>
  <div>
    <h2 class="page-title">
      Komens
      <span v-if="komens?.unread_count" class="badge badge--accent" style="margin-left: var(--space-sm);">
        {{ komens.unread_count }} nepřečtených
      </span>
    </h2>
    <div v-if="komens" class="search-bar">
      <input
        v-model="search"
        type="text"
        class="search-input glass-btn"
        placeholder="Hledat ve zprávách…"
      />
      <span v-if="search" class="search-count">{{ filteredMessages.length }} výsledků</span>
    </div>
    <div v-if="komens" class="timeline">
      <div v-for="group in groupedByDay" :key="group.label" class="timeline__day">
        <div class="timeline__date-col">
          <span class="timeline__date">{{ group.label }}</span>
          <div class="timeline__line"></div>
        </div>
        <div class="timeline__messages">
          <div
            v-for="m in group.messages"
            :key="m.id"
            class="msg inner-card"
            :class="{ 'msg--unread': !m.is_read }"
            @click="toggle(m.id)"
          >
            <div class="msg__header">
              <strong class="msg__title" :class="{ 'msg__title--unread': !m.is_read }">{{ m.title }}</strong>
              <span class="msg__time">{{ m.date ? new Date(m.date).toLocaleTimeString('cs', { hour: '2-digit', minute: '2-digit' }) : '' }}</span>
            </div>
            <div class="msg__sender">{{ m.sender }}</div>
            <p class="msg__text" :class="{ 'msg__text--expanded': expanded.has(m.id) }">{{ m.text }}</p>
            <span v-if="m.text?.length > 200" class="msg__toggle">
              {{ expanded.has(m.id) ? 'Méně' : 'Více' }}
            </span>
          </div>
        </div>
      </div>
    </div>
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

.msg {
  cursor: pointer;
  transition: border-color var(--transition);
}
.msg:hover { border-color: rgba(255, 255, 255, 0.12); }
.msg--unread { border-left: 2px solid var(--accent); }

.msg__header { display: flex; justify-content: space-between; align-items: baseline; }
.msg__title { font-size: var(--font-size-base); font-weight: var(--font-weight-medium); }
.msg__title--unread { font-weight: var(--font-weight-semibold); }
.msg__time { color: var(--text-muted); font-size: var(--font-size-sm); flex-shrink: 0; margin-left: var(--space-sm); }
.msg__sender { color: var(--text-secondary); font-size: var(--font-size-sm); margin: var(--space-xs) 0 var(--space-sm); }

.msg__text {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  line-height: 1.5;
  white-space: pre-line;
  max-height: 4.5em;
  overflow: hidden;
}
.msg__text--expanded { max-height: none; }

.msg__toggle {
  display: inline-block;
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--accent);
  cursor: pointer;
}

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
