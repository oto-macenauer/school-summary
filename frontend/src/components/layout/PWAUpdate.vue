<script setup lang="ts">
import { ref, onMounted } from 'vue'

const showUpdate = ref(false)
let waitingWorker: ServiceWorker | null = null

onMounted(() => {
  if (!('serviceWorker' in navigator)) return

  navigator.serviceWorker.ready.then((reg) => {
    reg.addEventListener('updatefound', () => {
      const newWorker = reg.installing
      if (!newWorker) return

      newWorker.addEventListener('statechange', () => {
        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
          waitingWorker = newWorker
          showUpdate.value = true
        }
      })
    })
  })

  // Also detect if there's already a waiting worker
  navigator.serviceWorker.ready.then((reg) => {
    if (reg.waiting) {
      waitingWorker = reg.waiting
      showUpdate.value = true
    }
  })
})

function update() {
  if (waitingWorker) {
    waitingWorker.postMessage({ type: 'SKIP_WAITING' })
  }
  showUpdate.value = false
  // Reload once the new SW activates
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    window.location.reload()
  })
}

function dismiss() {
  showUpdate.value = false
}
</script>

<template>
  <Transition name="slide">
    <div v-if="showUpdate" class="pwa-update">
      <span>Nová verze aplikace je dostupná</span>
      <div class="pwa-update__actions">
        <button class="glass-btn pwa-update__btn" @click="update">Aktualizovat</button>
        <button class="pwa-update__dismiss" @click="dismiss">&times;</button>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.pwa-update {
  position: fixed;
  bottom: var(--space-lg);
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  background: var(--bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  backdrop-filter: blur(var(--blur));
  -webkit-backdrop-filter: blur(var(--blur));
  box-shadow: var(--glass-shadow);
  z-index: 200;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}
.pwa-update__actions { display: flex; align-items: center; gap: var(--space-sm); }
.pwa-update__btn {
  background: var(--accent);
  color: #fff;
  padding: var(--space-xs) var(--space-md);
  font-size: var(--font-size-sm);
}
.pwa-update__dismiss {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 1.2rem;
  cursor: pointer;
  padding: 0 var(--space-xs);
}
.pwa-update__dismiss:hover { color: var(--text-secondary); }

.slide-enter-active, .slide-leave-active { transition: all 0.3s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(-50%) translateY(100%); opacity: 0; }
</style>
