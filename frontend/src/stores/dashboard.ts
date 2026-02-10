import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getDashboard } from '@/api/client'
import type { DashboardData } from '@/types'

export const useDashboardStore = defineStore('dashboard', () => {
  const data = ref<DashboardData | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(student: string) {
    loading.value = true
    error.value = null
    try {
      data.value = await getDashboard(student)
    } catch (e: any) {
      error.value = e.message || 'Failed to load dashboard'
    } finally {
      loading.value = false
    }
  }

  return { data, loading, error, load }
})
