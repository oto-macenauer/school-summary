import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getStudents } from '@/api/client'

export const useStudentStore = defineStore('student', () => {
  const students = ref<string[]>([])
  const current = ref<string>('')

  async function loadStudents() {
    students.value = await getStudents()
    if (students.value.length > 0 && !current.value) {
      current.value = students.value[0]
    }
  }

  function selectStudent(name: string) {
    current.value = name
  }

  return { students, current, loadStudents, selectStudent }
})
