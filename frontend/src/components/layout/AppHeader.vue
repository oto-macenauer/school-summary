<script setup lang="ts">
import { ref, computed } from 'vue'
import { useStudentStore } from '@/stores/student'
import { useRouter, useRoute } from 'vue-router'

const store = useStudentStore()
const router = useRouter()
const route = useRoute()
const menuOpen = ref(false)

const slug = computed(() => (store.current || '').toLowerCase())

const navLinks = computed(() => {
  const s = slug.value
  return [
    { to: `/${s}`, label: 'Dashboard', name: 'dashboard' },
    { to: `/${s}/timetable`, label: 'Rozvrh', name: 'timetable' },
    { to: `/${s}/marks`, label: 'Známky', name: 'marks' },
    { to: `/${s}/komens`, label: 'Komens', name: 'komens' },
    { to: `/${s}/mail`, label: 'Mail', name: 'mail' },
    { to: `/${s}/canteen`, label: 'Jídelníček', name: 'canteen' },
    { to: `/${s}/reports`, label: 'Reporty', name: 'reports' },
    { to: `/${s}/prompt`, label: 'AI Dotaz', name: 'prompt' },
  ]
})

function onStudentChange(name: string) {
  const currentName = route.name as string
  const lc = name.toLowerCase()
  if (currentName && currentName !== 'admin') {
    router.push({ name: currentName, params: { student: lc } })
  } else {
    router.push({ name: 'dashboard', params: { student: lc } })
  }
}

function onSelectChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  onStudentChange(value)
  closeMenu()
}

function closeMenu() {
  menuOpen.value = false
}
</script>

<template>
  <header class="header">
    <div class="header__left">
      <RouterLink :to="`/${slug}`" class="header__logo" @click="closeMenu">Bakalari</RouterLink>
      <button class="header__burger" :class="{ 'header__burger--open': menuOpen }" @click="menuOpen = !menuOpen" aria-label="Menu">
        <span></span><span></span><span></span>
      </button>
    </div>

    <nav class="header__nav" :class="{ 'header__nav--open': menuOpen }">
      <RouterLink
        v-for="link in navLinks"
        :key="link.name"
        :to="link.to"
        class="header__link"
        @click="closeMenu"
      >{{ link.label }}</RouterLink>

      <!-- Student selector inside mobile menu -->
      <div class="header__mobile-meta">
        <select
          v-if="store.students.length > 1"
          :value="store.current"
          @change="onSelectChange($event)"
          class="glass-btn header__select header__select--mobile"
        >
          <option v-for="s in store.students" :key="s" :value="s">{{ s }}</option>
        </select>
        <span v-else-if="store.current" class="header__student">{{ store.current }}</span>
        <RouterLink to="/admin" class="glass-btn" @click="closeMenu">Admin</RouterLink>
      </div>
    </nav>

    <div class="header__right">
      <select
        v-if="store.students.length > 1"
        :value="store.current"
        @change="onSelectChange($event)"
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
  -webkit-backdrop-filter: blur(var(--blur));
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

/* Hamburger button — hidden on desktop */
.header__burger {
  display: none;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  width: 32px;
  height: 32px;
  padding: 4px;
  background: none;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.header__burger span {
  display: block;
  width: 100%;
  height: 2px;
  background: var(--text-primary);
  border-radius: 1px;
  transition: all 0.25s ease;
}
.header__burger--open span:nth-child(1) { transform: translateY(7px) rotate(45deg); }
.header__burger--open span:nth-child(2) { opacity: 0; }
.header__burger--open span:nth-child(3) { transform: translateY(-7px) rotate(-45deg); }

/* Desktop nav */
.header__nav { display: flex; gap: var(--space-xs); }

.header__link {
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  text-decoration: none;
  transition: all var(--transition);
}
.header__link:hover, .header__link.router-link-exact-active {
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

/* Student selector + admin inside mobile menu — hidden on desktop */
.header__mobile-meta { display: none; }

/* ── Mobile ── */
@media (max-width: 768px) {
  .header {
    flex-wrap: wrap;
    padding: var(--space-sm) var(--space-md);
  }

  .header__burger { display: flex; }
  .header__right { display: none; }

  .header__nav {
    display: none;
    flex-direction: column;
    width: 100%;
    padding-top: var(--space-md);
    gap: 2px;
  }
  .header__nav--open { display: flex; }

  .header__link {
    padding: var(--space-md);
    border-radius: var(--radius-sm);
    font-size: var(--font-size-base);
  }
  .header__link:hover, .header__link.router-link-exact-active {
    background: rgba(255,255,255,0.08);
  }

  .header__mobile-meta {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    padding: var(--space-md);
    padding-top: var(--space-lg);
    border-top: 1px solid var(--glass-border);
    margin-top: var(--space-sm);
  }

  .header__select--mobile {
    flex: 1;
    min-height: 44px;
    font-size: var(--font-size-base);
  }
}
</style>
