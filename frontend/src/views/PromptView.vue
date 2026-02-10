<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { marked } from 'marked'
import { useStudentStore } from '@/stores/student'
import { sendPrompt, getPromptVariables } from '@/api/client'
import type { PromptVariable } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'

interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  resolvedVars?: string[]
  timestamp: Date
}

const store = useStudentStore()
const promptText = ref('')
const systemInstruction = ref('')
const showSystem = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const variables = ref<PromptVariable[]>([])
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const messagesEndRef = ref<HTMLDivElement | null>(null)
const messages = ref<ChatMessage[]>([])
let nextId = 1

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

function renderMarkdown(content: string): string {
  return marked.parse(content) as string
}

function scrollToBottom() {
  nextTick(() => {
    messagesEndRef.value?.scrollIntoView({ behavior: 'smooth' })
  })
}

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

  const userMsg: ChatMessage = {
    id: nextId++,
    role: 'user',
    content: promptText.value,
    timestamp: new Date(),
  }
  messages.value.push(userMsg)

  const prompt = promptText.value
  promptText.value = ''
  loading.value = true
  error.value = null
  scrollToBottom()

  try {
    const data = await sendPrompt(
      store.current,
      prompt,
      systemInstruction.value || undefined,
    )
    messages.value.push({
      id: nextId++,
      role: 'assistant',
      content: data.result,
      resolvedVars: data.resolved_variables,
      timestamp: new Date(),
    })
  } catch (e: any) {
    error.value = e.response?.data?.detail || e.message || 'Chyba při odesílání'
  } finally {
    loading.value = false
    scrollToBottom()
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
        <!-- Chat messages area -->
        <div class="chat-container">
          <div class="chat-messages">
            <div v-if="!messages.length && !loading" class="chat-empty">
              Zadejte dotaz a použijte {proměnné} pro vložení dat.
            </div>

            <div
              v-for="msg in messages"
              :key="msg.id"
              :class="['chat-bubble', `chat-bubble--${msg.role}`]"
            >
              <div class="chat-bubble__header">
                <span class="chat-bubble__role">{{ msg.role === 'user' ? 'Vy' : 'AI' }}</span>
                <span class="chat-bubble__time">
                  {{ msg.timestamp.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' }) }}
                </span>
              </div>
              <div
                v-if="msg.role === 'assistant'"
                class="chat-bubble__content markdown-body"
                v-html="renderMarkdown(msg.content)"
              ></div>
              <div v-else class="chat-bubble__content chat-bubble__content--user">{{ msg.content }}</div>
              <div v-if="msg.resolvedVars?.length" class="chat-bubble__meta">
                <span v-for="v in msg.resolvedVars" :key="v" class="badge badge--accent">{{ v }}</span>
              </div>
            </div>

            <div v-if="loading" class="chat-bubble chat-bubble--assistant chat-bubble--loading">
              <LoadingSpinner />
            </div>

            <div ref="messagesEndRef"></div>
          </div>
        </div>

        <!-- Error display -->
        <p v-if="error" class="prompt-error">{{ error }}</p>

        <!-- Input area -->
        <div class="chat-input">
          <textarea
            v-if="showSystem"
            v-model="systemInstruction"
            class="prompt-textarea prompt-textarea--sm"
            placeholder="Volitelná systémová instrukce pro AI..."
            rows="2"
          ></textarea>
          <div class="chat-input__row">
            <textarea
              ref="textareaRef"
              v-model="promptText"
              class="prompt-textarea"
              placeholder="Napište svůj dotaz... Použijte {proměnné} pro vložení dat."
              rows="3"
              @keydown.ctrl.enter="submit"
            ></textarea>
            <button
              class="glass-btn glass-btn--accent chat-send-btn"
              :disabled="loading || !promptText.trim() || !store.current"
              @click="submit"
            >Odeslat</button>
          </div>
          <div class="chat-input__actions">
            <button
              class="glass-btn prompt-toggle"
              @click="showSystem = !showSystem"
            >{{ showSystem ? 'Skrýt instrukci' : 'Systémová instrukce' }}</button>
          </div>
        </div>
      </div>

      <!-- Sidebar -->
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
.prompt-page { padding: var(--space-lg) var(--space-xl); height: calc(100vh - 4rem); display: flex; flex-direction: column; box-sizing: border-box; }
.page-title { flex-shrink: 0; }

.prompt-layout {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: var(--space-lg);
  flex: 1;
  min-height: 0;
}
@media (max-width: 900px) { .prompt-layout { grid-template-columns: 1fr; } }

.prompt-main {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* Chat messages container */
.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-md);
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-md);
}

.chat-messages {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  min-height: 100%;
}

.chat-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-height: 200px;
  color: var(--text-muted);
  font-size: var(--font-size-base);
  text-align: center;
}

/* Chat bubbles */
.chat-bubble {
  max-width: 85%;
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
}

.chat-bubble--user {
  align-self: flex-end;
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.2);
}

.chat-bubble--assistant {
  align-self: flex-start;
  background: rgba(255, 255, 255, 0.04);
}

.chat-bubble--loading {
  display: flex;
  justify-content: center;
  padding: var(--space-md);
}

.chat-bubble__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-xs);
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.chat-bubble__role { font-weight: var(--font-weight-semibold); }

.chat-bubble__content {
  font-size: var(--font-size-base);
  line-height: 1.6;
}

.chat-bubble__content--user {
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-bubble__content.markdown-body :deep(p) { margin: 0 0 0.5em; }
.chat-bubble__content.markdown-body :deep(p:last-child) { margin-bottom: 0; }
.chat-bubble__content.markdown-body :deep(ul) { margin: 0.25em 0; padding-left: 1.5em; }
.chat-bubble__content.markdown-body :deep(ol) { margin: 0.25em 0; padding-left: 1.5em; }
.chat-bubble__content.markdown-body :deep(li) { margin: 0.15em 0; }
.chat-bubble__content.markdown-body :deep(strong) { font-weight: 600; }
.chat-bubble__content.markdown-body :deep(h2) { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); margin: 0.75em 0 0.25em; }
.chat-bubble__content.markdown-body :deep(h3) { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); margin: 0.5em 0 0.25em; }
.chat-bubble__content.markdown-body :deep(code) { background: rgba(255,255,255,0.06); padding: 0.1em 0.3em; border-radius: 3px; font-size: 0.9em; }

.chat-bubble__meta {
  display: flex;
  gap: var(--space-xs);
  flex-wrap: wrap;
  margin-top: var(--space-xs);
  padding-top: var(--space-xs);
  border-top: 1px solid var(--glass-border);
  font-size: var(--font-size-xs);
}

/* Input area */
.chat-input {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.chat-input__row {
  display: flex;
  gap: var(--space-sm);
  align-items: flex-end;
}

.chat-input__row .prompt-textarea { flex: 1; }

.chat-send-btn { flex-shrink: 0; align-self: flex-end; }

.chat-input__actions { display: flex; justify-content: flex-start; }

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
.prompt-textarea--sm { min-height: 3rem; font-size: var(--font-size-sm); }

.prompt-toggle { font-size: var(--font-size-sm); }

.prompt-error {
  color: var(--error);
  font-size: var(--font-size-base);
  padding: var(--space-md);
  background: rgba(239, 68, 68, 0.08);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(239, 68, 68, 0.2);
  flex-shrink: 0;
}

/* Sidebar */
.prompt-sidebar { overflow-y: auto; }

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
