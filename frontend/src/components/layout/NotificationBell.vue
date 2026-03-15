<script setup lang="ts">
import { onMounted } from 'vue'
import { useStudentStore } from '@/stores/student'
import { useNotifications } from '@/composables/useNotifications'

const store = useStudentStore()
const { supported, permission, isSubscribed, loading, subscribe, unsubscribe, checkExistingSubscription } = useNotifications()

onMounted(() => {
  if (supported) {
    checkExistingSubscription()
  }
})

async function toggle() {
  if (!store.current) return
  if (isSubscribed.value) {
    await unsubscribe(store.current)
  } else {
    await subscribe(store.current)
  }
}
</script>

<template>
  <button
    v-if="supported"
    class="notification-bell"
    :class="{
      'notification-bell--active': isSubscribed,
      'notification-bell--denied': permission === 'denied',
    }"
    :disabled="loading || permission === 'denied'"
    :title="permission === 'denied' ? 'Notifikace zakázány v nastavení prohlížeče' : isSubscribed ? 'Vypnout notifikace' : 'Zapnout notifikace'"
    @click="toggle"
  >
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
      <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
      <line v-if="isSubscribed" x1="1" y1="1" x2="23" y2="23" stroke-width="0"/>
    </svg>
    <span v-if="isSubscribed" class="notification-bell__dot"/>
  </button>
</template>

<style scoped>
.notification-bell {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition);
}
.notification-bell:hover { color: var(--text-primary); background: rgba(255,255,255,0.08); }
.notification-bell--active { color: var(--accent); }
.notification-bell--denied { opacity: 0.4; cursor: not-allowed; }
.notification-bell:disabled { pointer-events: none; }

.notification-bell__dot {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 7px;
  height: 7px;
  background: var(--accent);
  border-radius: 50%;
}
</style>
