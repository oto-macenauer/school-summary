import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
    { path: '/timetable', name: 'timetable', component: () => import('@/views/TimetableView.vue') },
    { path: '/marks', name: 'marks', component: () => import('@/views/MarksView.vue') },
    { path: '/komens', name: 'komens', component: () => import('@/views/KomensView.vue') },
    { path: '/reporty', name: 'reporty', component: () => import('@/views/GDriveView.vue') },
    { path: '/prompt', name: 'prompt', component: () => import('@/views/PromptView.vue') },
    { path: '/admin', name: 'admin', component: () => import('@/views/AdminView.vue') },
  ],
})

export default router
