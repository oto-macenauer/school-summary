<script setup lang="ts">
import { useStudentStore } from '@/stores/student'
import type { DashboardResources, ResourceCategory } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'

defineProps<{ data: DashboardResources | null }>()

const store = useStudentStore()

const categoryLabels: Record<ResourceCategory, string> = {
  komens: 'Komens',
  mail: 'Mail',
  report: 'Report',
}
</script>

<template>
  <GlassCard title="Zprávy">
    <template v-if="data?.recent.length">
      <div class="res-header">
        <span v-if="data.unread_count" class="badge badge--accent">{{ data.unread_count }} nepřečtených</span>
        <RouterLink
          :to="{ name: 'resources', params: { student: store.current?.toLowerCase() } }"
          class="res-all"
        >
          Všechny ({{ data.total }})
        </RouterLink>
      </div>
      <div class="messages">
        <RouterLink
          v-for="m in data.recent"
          :key="m.id"
          :to="{ name: 'resources', params: { student: store.current?.toLowerCase() }, hash: `#${m.id}` }"
          class="msg"
          :class="{ 'msg--unread': m.isRead === false }"
        >
          <div class="msg__top">
            <span class="msg__tag" :class="`msg__tag--${m.category}`">{{ categoryLabels[m.category] }}</span>
            <span class="msg__title">{{ m.title }}</span>
            <span class="msg__date">{{ m.date ? new Date(m.date).toLocaleDateString('cs') : '' }}</span>
          </div>
          <span v-if="m.sender" class="msg__sender">{{ m.sender }}</span>
          <p class="msg__preview">{{ m.preview }}</p>
        </RouterLink>
      </div>
    </template>
    <p v-else class="empty">Žádné zprávy</p>
  </GlassCard>
</template>

<style scoped>
.res-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}
.res-all {
  margin-left: auto;
  font-size: var(--font-size-sm);
  color: var(--accent-text);
}
.messages { display: flex; flex-direction: column; gap: var(--space-xs); max-width: 100%; }
.msg {
  display: block;
  padding: var(--space-sm) 0;
  border-bottom: var(--border-subtle);
  font-size: var(--font-size-base);
  text-decoration: none;
  color: inherit;
  transition: background var(--transition);
}
.msg:last-child { border-bottom: none; }
.msg:hover { background: rgba(255, 255, 255, 0.05); text-decoration: none; }
.msg--unread .msg__title { font-weight: var(--font-weight-semibold); }
.msg__top { display: flex; align-items: baseline; gap: var(--space-sm); min-width: 0; }
.msg__tag {
  font-size: var(--font-size-xs);
  padding: 1px var(--space-xs);
  border-radius: 4px;
  flex-shrink: 0;
  font-weight: var(--font-weight-medium);
}
.msg__tag--komens { background: var(--accent-soft); color: var(--accent-text); }
.msg__tag--mail { background: rgba(52, 211, 153, 0.2); color: var(--success-text); }
.msg__tag--report { background: rgba(251, 191, 36, 0.2); color: var(--warning-text); }
.msg__title { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.msg__date { color: var(--text-muted); font-size: var(--font-size-xs); flex-shrink: 0; }
.msg__sender {
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  display: block;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.msg__preview {
  color: var(--text-muted);
  font-size: var(--font-size-sm);
  margin-top: var(--space-xs);
  line-height: 1.4;
  /* Previews come straight from Komens/mail bodies — break anything */
  overflow-wrap: anywhere;
  word-break: break-word;
}
.empty { color: var(--text-muted); font-size: var(--font-size-base); }
</style>
