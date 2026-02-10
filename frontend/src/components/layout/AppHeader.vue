<script setup lang="ts">
import { onMounted } from 'vue'
import { useStudentStore } from '@/stores/student'
import { useRouter } from 'vue-router'

const store = useStudentStore()
const router = useRouter()

onMounted(() => { store.loadStudents() })
</script>

<template>
  <header class="header">
    <div class="header__left">
      <RouterLink to="/" class="header__logo">Bakalari</RouterLink>
      <nav class="header__nav">
        <RouterLink to="/" class="header__link">Dashboard</RouterLink>
        <RouterLink to="/timetable" class="header__link">Rozvrh</RouterLink>
        <RouterLink to="/marks" class="header__link">Známky</RouterLink>
        <RouterLink to="/komens" class="header__link">Komens</RouterLink>
        <RouterLink to="/reporty" class="header__link">Reporty</RouterLink>
        <RouterLink to="/prompt" class="header__link">AI Dotaz</RouterLink>
      </nav>
    </div>
    <div class="header__right">
      <select
        v-if="store.students.length > 1"
        :value="store.current"
        @change="store.selectStudent(($event.target as HTMLSelectElement).value)"
        class="glass-btn header__select"
      >
        <option v-for="s in store.students" :key="s" :value="s">{{ s }}</option>
      </select>
      <span v-else-if="store.current" class="header__student">{{ store.current }}</span>
      <RouterLink to="/admin" class="glass-btn">Admin</RouterLink>
    </div>
  </header>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-md) var(--space-xl);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--blur));
  border-bottom: 1px solid var(--glass-border);
  position: sticky;
  top: 0;
  z-index: 100;
}
.header__left { display: flex; align-items: center; gap: var(--space-xl); }
.header__logo {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  text-decoration: none;
}
.header__nav { display: flex; gap: var(--space-xs); }
.header__link {
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  text-decoration: none;
  transition: all var(--transition);
}
.header__link:hover, .header__link.router-link-active {
  color: var(--text-primary);
  background: rgba(255,255,255,0.06);
}
.header__right { display: flex; align-items: center; gap: var(--space-sm); }
.header__student { color: var(--text-secondary); font-size: var(--font-size-base); }
.header__select {
  background: var(--glass-bg);
  color: var(--text-primary);
  appearance: auto;
}
.header__select option { background: var(--bg-secondary); color: var(--text-primary); }
</style>
