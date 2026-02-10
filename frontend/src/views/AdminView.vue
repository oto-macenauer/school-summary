<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getLogs, getSchedulerStatus, getConfig, getGeminiUsage, reloadConfig } from '@/api/client'
import type { LogEntry, TaskStatus } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'

const tab = ref<'scheduler' | 'logs' | 'config' | 'gemini'>('scheduler')
const tasks = ref<TaskStatus[]>([])
const logs = ref<LogEntry[]>([])
const categories = ref<string[]>([])
const logCategory = ref('')
const logLevel = ref('')
const config = ref<any>(null)
const gemini = ref<any>(null)

async function loadScheduler() {
  const data = await getSchedulerStatus()
  tasks.value = data.tasks
}

async function loadLogs() {
  const params: any = { limit: 200 }
  if (logCategory.value) params.category = logCategory.value
  if (logLevel.value) params.level = logLevel.value
  const data = await getLogs(params)
  logs.value = data.entries
  categories.value = data.categories
}

async function loadConfig() { config.value = await getConfig() }
async function loadGemini() { gemini.value = await getGeminiUsage() }

async function doReload() {
  await reloadConfig()
  await loadConfig()
}

onMounted(async () => {
  await Promise.all([loadScheduler(), loadLogs(), loadConfig(), loadGemini()])
})

const navItems = [
  { key: 'scheduler' as const, label: 'Scheduler' },
  { key: 'logs' as const, label: 'Logy' },
  { key: 'config' as const, label: 'Konfigurace' },
  { key: 'gemini' as const, label: 'Gemini' },
]
</script>

<template>
  <div class="admin">
    <nav class="admin__nav">
      <h3 class="admin__nav-title">Administrace</h3>
      <button
        v-for="item in navItems"
        :key="item.key"
        class="admin__nav-item"
        :class="{ 'admin__nav-item--active': tab === item.key }"
        @click="tab = item.key"
      >{{ item.label }}</button>
    </nav>

    <div class="admin__content">
      <!-- Scheduler -->
      <div v-if="tab === 'scheduler'" class="section">
        <div
          v-for="t in tasks"
          :key="t.task_name + t.student"
          class="inner-card task-card"
        >
          <div class="task-header">
            <div class="task-name">
              <strong>{{ t.task_name }}</strong>
              <span class="task-student">{{ t.student }}</span>
            </div>
            <span class="badge" :class="{
              'badge--success': t.last_status === 'success',
              'badge--error': t.last_status === 'error',
              'badge--warning': t.last_status === 'pending',
            }">{{ t.last_status }}</span>
          </div>
          <div class="task-details">
            <span>Runs: {{ t.run_count }}</span>
            <span>Errors: {{ t.error_count }}</span>
            <span>Last: {{ t.last_duration_ms ?? '–' }}ms</span>
            <span>Next: {{ t.next_run ? new Date(t.next_run).toLocaleTimeString('cs') : '–' }}</span>
          </div>
          <div v-if="t.last_error" class="task-error">{{ t.last_error }}</div>
        </div>
      </div>

      <!-- Logs -->
      <div v-if="tab === 'logs'" class="section">
        <div class="log-filters">
          <select v-model="logCategory" @change="loadLogs()" class="glass-btn">
            <option value="">Všechny kategorie</option>
            <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
          </select>
          <select v-model="logLevel" @change="loadLogs()" class="glass-btn">
            <option value="">Všechny úrovně</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
        </div>
        <GlassCard>
          <div class="log-list">
            <div v-for="(l, i) in logs" :key="i" class="log-entry">
              <span class="log-time">{{ new Date(l.timestamp).toLocaleTimeString('cs') }}</span>
              <span class="badge" :class="{
                'badge--success': l.level === 'INFO',
                'badge--warning': l.level === 'WARNING',
                'badge--error': l.level === 'ERROR',
              }">{{ l.level }}</span>
              <span class="log-cat">{{ l.category }}</span>
              <span class="log-msg">{{ l.message }}</span>
            </div>
          </div>
        </GlassCard>
      </div>

      <!-- Config -->
      <div v-if="tab === 'config'" class="section">
        <div class="config-actions">
          <button class="glass-btn glass-btn--accent" @click="doReload">Reload</button>
          <span v-if="config?.config_path" class="config-path">{{ config.config_path }}</span>
        </div>
        <GlassCard>
          <pre class="config-pre">{{ config?.config ? JSON.stringify(config.config, null, 2) : 'Loading...' }}</pre>
        </GlassCard>
      </div>

      <!-- Gemini -->
      <div v-if="tab === 'gemini'" class="section">
        <GlassCard title="Gemini API Usage" v-if="gemini && !gemini.error">
          <div class="usage-row">
            <span>Požadavky dnes</span>
            <div class="progress-bar"><div class="progress-fill" :style="{ width: ((gemini.requests_today / gemini.requests_limit) * 100) + '%' }"></div></div>
            <span>{{ gemini.requests_today }} / {{ gemini.requests_limit }}</span>
          </div>
          <div class="usage-row">
            <span>Tokeny dnes</span>
            <div class="progress-bar"><div class="progress-fill" :style="{ width: ((gemini.tokens_today / gemini.tokens_limit) * 100) + '%' }"></div></div>
            <span>{{ gemini.tokens_today?.toLocaleString() }} / {{ gemini.tokens_limit?.toLocaleString() }}</span>
          </div>
        </GlassCard>
        <GlassCard v-else title="Gemini">
          <p class="empty">Gemini není nakonfigurováno</p>
        </GlassCard>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin {
  display: grid;
  grid-template-columns: 12rem 1fr;
  gap: var(--space-xl);
  min-height: calc(100vh - 6rem);
}

@media (max-width: 768px) {
  .admin { grid-template-columns: 1fr; }
  .admin__nav { flex-direction: row; overflow-x: auto; }
}

/* Left sidebar nav */
.admin__nav {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  position: sticky;
  top: 5rem;
  align-self: start;
}
.admin__nav-title {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-secondary);
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-xs);
}
.admin__nav-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: var(--space-sm) var(--space-md);
  border: none;
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--font-size-base);
  font-family: var(--font-family);
  cursor: pointer;
  transition: all var(--transition);
}
.admin__nav-item:hover { color: var(--text-primary); background: rgba(255, 255, 255, 0.04); }
.admin__nav-item--active {
  color: var(--text-primary);
  background: rgba(99, 102, 241, 0.12);
  font-weight: var(--font-weight-medium);
}

/* Content */
.admin__content { min-width: 0; }
.section { display: flex; flex-direction: column; gap: var(--space-sm); }

/* Scheduler */
.task-card { margin-bottom: 0; }
.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.task-name { font-size: var(--font-size-base); }
.task-student { color: var(--text-muted); margin-left: var(--space-sm); font-size: var(--font-size-sm); }
.task-details {
  display: flex;
  gap: var(--space-lg);
  margin-top: var(--space-sm);
  padding-top: var(--space-sm);
  border-top: var(--border-subtle);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}
.task-error {
  font-size: var(--font-size-sm);
  color: var(--error);
  margin-top: var(--space-xs);
}

/* Logs */
.log-filters { display: flex; gap: var(--space-sm); margin-bottom: var(--space-md); }
.log-list { font-family: var(--font-mono); font-size: var(--font-size-sm); }
.log-entry {
  display: flex;
  gap: var(--space-sm);
  align-items: baseline;
  padding: var(--space-sm) 0;
  border-bottom: var(--border-subtle);
}
.log-entry:last-child { border-bottom: none; }
.log-time { color: var(--text-muted); min-width: 5rem; }
.log-cat { color: var(--text-secondary); min-width: 6rem; }
.log-msg { flex: 1; color: var(--text-primary); }

/* Config */
.config-actions {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  margin-bottom: var(--space-sm);
}
.config-path { color: var(--text-muted); font-size: var(--font-size-sm); }
.config-pre {
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  overflow-x: auto;
  white-space: pre-wrap;
}

/* Gemini */
.usage-row {
  display: flex;
  align-items: center;
  gap: var(--space-lg);
  margin: var(--space-sm) 0;
  font-size: var(--font-size-base);
}
.usage-row span:first-child { min-width: 8rem; color: var(--text-secondary); }
.progress-bar { flex: 1; height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.3s; }
.empty { color: var(--text-muted); font-size: var(--font-size-base); }
</style>
