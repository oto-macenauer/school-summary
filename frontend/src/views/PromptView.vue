<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { marked } from 'marked'
import { useStudentStore } from '@/stores/student'
import { sendPrompt, getPromptVariables } from '@/api/client'
import type { PromptVariable } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'

const store = useStudentStore()
const promptText = ref('')
const systemInstruction = ref('')
const showSystem = ref(false)
const result = ref('')
const resolvedVars = ref<string[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const variables = ref<PromptVariable[]>([])
const textareaRef = ref<HTMLTextAreaElement | null>(null)

const categories: Record<string, string> = {
  timetable: 'Rozvrh',
  marks: 'Známky',
  komens: 'Komens',
  gdrive: 'Reporty',
  summary: 'Shrnutí',
  prepare: 'Příprava',
}

const groupedVariables = computed(() => {
  const groups: Record<string, PromptVariable[]> = {}
  for (const v of variables.value) {
    const label = categories[v.category] || v.category
    if (!groups[label]) groups[label] = []
    groups[label].push(v)
  }
  return groups
})

const renderedResult = computed(() => {
  if (!result.value) return ''
  return marked.parse(result.value) as string
})

async function loadVariables() {
  if (!store.current) return
  try {
    const data = await getPromptVariables(store.current)
    variables.value = data.variables
  } catch {
    variables.value = []
  }
}

async function submit() {
  if (!store.current || !promptText.value.trim()) return
  loading.value = true
  error.value = null
  result.value = ''
  resolvedVars.value = []
  try {
    const data = await sendPrompt(
      store.current,
      promptText.value,
      systemInstruction.value || undefined,
    )
    result.value = data.result
    resolvedVars.value = data.resolved_variables
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || 'Chyba při odesílání'
  } finally {
    loading.value = false
  }
}

function insertVariable(name: string) {
  const el = textareaRef.value
  const tag = `{${name}}`
  if (el) {
    const start = el.selectionStart
    const end = el.selectionEnd
    promptText.value =
      promptText.value.substring(0, start) + tag + promptText.value.substring(end)
    nextTick(() => {
      const pos = start + tag.length
      el.focus()
      el.setSelectionRange(pos, pos)
    })
  } else {
    promptText.value += tag
  }
}

onMounted(loadVariables)
watch(() => store.current, loadVariables)
</script>

<template>
  <div class="prompt-page">
    <h1 class="page-title">AI Dotaz</h1>
    <div class="prompt-layout">
      <div class="prompt-main">
        <GlassCard title="Prompt">
          <div class="prompt-editor">
            <textarea
              ref="textareaRef"
              v-model="promptText"
              class="prompt-textarea"
              placeholder="Napište svůj dotaz... Použijte {proměnné} pro vložení dat."
              rows="6"
              @keydown.ctrl.enter="submit"
            ></textarea>
            <div class="prompt-actions">
              <button
                class="glass-btn prompt-toggle"
                @click="showSystem = !showSystem"
              >{{ showSystem ? 'Skrýt' : 'Systémová instrukce' }}</button>
              <button
                class="glass-btn glass-btn--accent"
                :disabled="loading || !promptText.trim() || !store.current"
                @click="submit"
              >{{ loading ? 'Odesílám...' : 'Odeslat' }}</button>
            </div>
            <textarea
              v-if="showSystem"
              v-model="systemInstruction"
              class="prompt-textarea prompt-textarea--sm"
              placeholder="Volitelná systémová instrukce pro AI..."
              rows="3"
            ></textarea>
          </div>
        </GlassCard>

        <div v-if="loading" class="prompt-loading">
          <LoadingSpinner />
        </div>

        <p v-if="error" class="prompt-error">{{ error }}</p>

        <GlassCard v-if="result" title="Odpověď">
          <div class="prompt-result markdown-body" v-html="renderedResult"></div>
          <div v-if="resolvedVars.length" class="prompt-meta">
            Použité proměnné:
            <span v-for="v in resolvedVars" :key="v" class="badge badge--accent">{{ v }}</span>
          </div>
        </GlassCard>
      </div>

      <div class="prompt-sidebar">
        <GlassCard title="Proměnné">
          <p class="prompt-sidebar__hint">Kliknutím vložíte do promptu</p>
          <div v-for="(vars, group) in groupedVariables" :key="group" class="var-group">
            <h3 class="var-group__title">{{ group }}</h3>
            <div class="var-group__items">
              <button
                v-for="v in vars"
                :key="v.name"
                class="var-chip"
                :title="v.description"
                @click="insertVariable(v.name)"
              >{{ v.name }}</button>
            </div>
          </div>
          <p v-if="!variables.length" class="empty">Vyberte studenta pro zobrazení proměnných</p>
        </GlassCard>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prompt-page { padding: var(--space-lg) var(--space-xl); }
.prompt-layout {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: var(--space-lg);
  align-items: start;
}
@media (max-width: 900px) { .prompt-layout { grid-template-columns: 1fr; } }

.prompt-main { display: flex; flex-direction: column; gap: var(--space-lg); }

.prompt-editor { display: flex; flex-direction: column; gap: var(--space-sm); }

.prompt-textarea {
  width: 100%;
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  padding: var(--space-md);
  font-family: var(--font-family);
  font-size: var(--font-size-base);
  line-height: 1.5;
  resize: vertical;
  box-sizing: border-box;
}
.prompt-textarea:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}
.prompt-textarea--sm { min-height: 4rem; font-size: var(--font-size-sm); }

.prompt-actions { display: flex; justify-content: space-between; align-items: center; }
.prompt-toggle { font-size: var(--font-size-sm); }

.prompt-loading { display: flex; justify-content: center; padding: var(--space-xl) 0; }

.prompt-error {
  color: var(--error);
  font-size: var(--font-size-base);
  padding: var(--space-md);
  background: rgba(239, 68, 68, 0.08);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.prompt-result { font-size: var(--font-size-base); line-height: 1.6; }
.prompt-result :deep(p) { margin: 0 0 0.5em; }
.prompt-result :deep(ul) { margin: 0.25em 0; padding-left: 1.5em; }
.prompt-result :deep(ol) { margin: 0.25em 0; padding-left: 1.5em; }
.prompt-result :deep(li) { margin: 0.15em 0; }
.prompt-result :deep(strong) { font-weight: 600; }
.prompt-result :deep(h2) { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); margin: 0.75em 0 0.25em; }
.prompt-result :deep(h3) { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); margin: 0.5em 0 0.25em; }
.prompt-result :deep(code) { background: rgba(255,255,255,0.06); padding: 0.1em 0.3em; border-radius: 3px; font-size: 0.9em; }

.prompt-meta {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  flex-wrap: wrap;
  margin-top: var(--space-md);
  padding-top: var(--space-sm);
  border-top: 1px solid var(--glass-border);
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.prompt-sidebar__hint {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  margin-bottom: var(--space-md);
}

.var-group { margin-bottom: var(--space-md); }
.var-group:last-child { margin-bottom: 0; }
.var-group__title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-secondary);
  margin-bottom: var(--space-xs);
}
.var-group__items { display: flex; flex-wrap: wrap; gap: 4px; }
.var-chip {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: rgba(255,255,255,0.04);
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
  font-family: var(--font-family);
  cursor: pointer;
  transition: all var(--transition);
  white-space: nowrap;
}
.var-chip:hover {
  color: var(--text-primary);
  background: rgba(99, 102, 241, 0.12);
  border-color: var(--accent);
}

.empty { color: var(--text-muted); font-size: var(--font-size-sm); }
</style>
