import { createRouter, createWebHistory } from 'vue-router'
import { useStudentStore } from '@/stores/student'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/:student', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
    { path: '/:student/timetable', name: 'timetable', component: () => import('@/views/TimetableView.vue') },
    { path: '/:student/marks', name: 'marks', component: () => import('@/views/MarksView.vue') },
    { path: '/:student/komens', name: 'komens', component: () => import('@/views/KomensView.vue') },
    { path: '/:student/mail', name: 'mail', component: () => import('@/views/MailView.vue') },
    { path: '/:student/canteen', name: 'canteen', component: () => import('@/views/CanteenView.vue') },
    { path: '/:student/reports', name: 'reports', component: () => import('@/views/GDriveView.vue') },
    { path: '/:student/prompt', name: 'prompt', component: () => import('@/views/PromptView.vue') },
    { path: '/admin', name: 'admin', component: () => import('@/views/AdminView.vue') },
  ],
})

router.beforeEach(async (to) => {
  const store = useStudentStore()

  if (!store.students.length) {
    try {
      await store.loadStudents()
    } catch {
      // API not available — let admin through, redirect others
      if (to.name !== 'admin') {
        return { name: 'admin' }
      }
      return
    }
  }

  // Redirect bare "/" to first student's dashboard
  if (to.path === '/') {
    if (store.students.length) {
      return { name: 'dashboard', params: { student: store.students[0].toLowerCase() } }
    }
    return { name: 'admin' }
  }

  const studentParam = to.params.student as string | undefined
  if (!studentParam) return // non-student routes like /admin

  // Match case-insensitively: URL has "filip", store has "Filip"
  const match = store.students.find(s => s.toLowerCase() === studentParam.toLowerCase())
  if (match) {
    store.selectStudent(match)
  } else if (store.students.length) {
    // Unknown student name in URL — redirect to first student
    return { name: to.name!, params: { ...to.params, student: store.students[0].toLowerCase() } }
  }
})

export default router
