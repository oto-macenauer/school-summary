import axios from 'axios'
import type { CanteenData, DashboardData, GDriveReport, LogEntry, MailData, PromptResponse, PromptVariable, ResourceItem, TaskStatus } from '@/types'

const api = axios.create({ baseURL: '/api' })

export async function getStudents(): Promise<string[]> {
  const { data } = await api.get('/status')
  return Object.keys(data.students || {})
}

export async function getDashboard(student: string): Promise<DashboardData> {
  const { data } = await api.get(`/students/${student}/dashboard`)
  return data
}

export async function getTimetable(student: string, date?: string) {
  const params = date ? { date } : {}
  const { data } = await api.get(`/students/${student}/timetable`, { params })
  return data
}

export async function getMarks(student: string) {
  const { data } = await api.get(`/students/${student}/marks`)
  return data
}

export async function getKomens(student: string) {
  const { data } = await api.get(`/students/${student}/komens`)
  return data
}

export async function getMail(student: string): Promise<MailData> {
  const { data } = await api.get(`/students/${student}/mail`)
  return data
}

export async function getCanteen(): Promise<CanteenData> {
  const { data } = await api.get('/canteen')
  return data
}

export async function getGDriveReports(student: string): Promise<{ reports: GDriveReport[]; total: number }> {
  const { data } = await api.get(`/students/${student}/gdrive`)
  return data
}

export async function sendPrompt(student: string, prompt: string, systemInstruction?: string): Promise<PromptResponse> {
  const { data } = await api.post(`/students/${student}/prompt`, {
    prompt,
    system_instruction: systemInstruction || null,
  })
  return data
}

export async function getPromptVariables(student: string): Promise<{ variables: PromptVariable[] }> {
  const { data } = await api.get(`/students/${student}/prompt/variables`)
  return data
}

export async function getSummary(student: string, period = 'current') {
  const { data } = await api.get(`/students/${student}/summary`, { params: { period } })
  return data
}

export async function getLogs(params: { category?: string; level?: string; limit?: number }) {
  const { data } = await api.get('/admin/logs', { params })
  return data as { entries: LogEntry[]; total: number; categories: string[] }
}

export async function getSchedulerStatus() {
  const { data } = await api.get('/admin/scheduler')
  return data as { tasks: TaskStatus[] }
}

export async function getConfig() {
  const { data } = await api.get('/config')
  return data
}

export async function getGeminiUsage() {
  const { data } = await api.get('/admin/gemini-usage')
  return data
}

export async function getResources(student: string): Promise<{
  items: ResourceItem[]
  available_tags: { subjects: string[]; importance: string[] }
}> {
  const { data } = await api.get(`/students/${student}/resources`)
  return data
}

export async function reloadConfig() {
  const { data } = await api.post('/config/reload')
  return data
}

export async function triggerTask(taskKey: string) {
  const { data } = await api.post(`/admin/scheduler/${taskKey}/trigger`)
  return data as { status: string; message: string; task: TaskStatus | null }
}

// Push notifications
export async function getVapidKey(): Promise<{ public_key: string }> {
  const { data } = await api.get('/notifications/vapid-key')
  return data
}

export async function subscribePush(student: string, subscription: PushSubscriptionJSON) {
  const { data } = await api.post('/notifications/subscribe', { student, subscription })
  return data
}

export async function unsubscribePush(student: string, endpoint: string) {
  const { data } = await api.post('/notifications/unsubscribe', { student, endpoint })
  return data
}
