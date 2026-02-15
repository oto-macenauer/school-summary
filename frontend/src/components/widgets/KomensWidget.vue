<script setup lang="ts">
import { useStudentStore } from '@/stores/student'
import type { KomensData } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'

defineProps<{ data: KomensData | null }>()

const store = useStudentStore()

function truncate(text: string, max: number): string {
  if (!text || text.length <= max) return text || ''
  return text.slice(0, max).trimEnd() + '\u2026'
}
</script>

<template>
  <GlassCard title="Komens">
    <template v-if="data">
      <div class="komens-header">
        <span v-if="data.unread_count" class="badge badge--accent">{{ data.unread_count }} nepřečtených</span>
      </div>
      <div class="messages">
        <RouterLink
          v-for="m in data.recent_messages?.slice(0, 5)"
          :key="m.id"
          :to="{ name: 'resources', params: { student: store.current?.toLowerCase() } }"
          class="msg"
          :class="{ 'msg--unread': !m.is_read }"
        >
          <div class="msg__top">
            <span class="msg__title">{{ m.title }}</span>
            <span class="msg__date">{{ m.date ? new Date(m.date).toLocaleDateString('cs') : '' }}</span>
          </div>
          <span class="msg__sender">{{ m.sender }}</span>
          <p class="msg__preview">{{ truncate(m.text, 120) }}</p>
        </RouterLink>
      </div>
    </template>
    <p v-else class="empty">Žádné zprávy</p>
  </GlassCard>
</template>

<style scoped>
.komens-header { margin-bottom: var(--space-sm); }
.messages { display: flex; flex-direction: column; gap: var(--space-xs); }
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
.msg:hover { background: rgba(255, 255, 255, 0.02); }
.msg--unread .msg__title { font-weight: var(--font-weight-semibold); }
.msg__top { display: flex; justify-content: space-between; align-items: baseline; }
.msg__title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.msg__date { color: var(--text-muted); font-size: var(--font-size-xs); flex-shrink: 0; margin-left: var(--space-sm); }
.msg__sender { color: var(--text-secondary); font-size: var(--font-size-sm); display: block; margin-top: 2px; }
.msg__preview { color: var(--text-muted); font-size: var(--font-size-sm); margin-top: var(--space-xs); line-height: 1.4; }
.empty { color: var(--text-muted); font-size: var(--font-size-base); }
</style>
