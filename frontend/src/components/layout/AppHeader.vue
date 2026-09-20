<script setup lang="ts">
import { ref, computed } from 'vue'
import { useStudentStore } from '@/stores/student'
import { useRouter, useRoute } from 'vue-router'
import NotificationBell from './NotificationBell.vue'

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
    { to: `/${s}/resources`, label: 'Zprávy', name: 'resources' },
    { to: `/${s}/canteen`, label: 'Jídelníček', name: 'canteen' },
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
    <div class="header__bar">
      <RouterLink :to="`/${slug}`" class="header__logo" @click="closeMenu">Školní přehled</RouterLink>

      <nav class="header__nav" aria-label="Hlavní navigace">
        <RouterLink
          v-for="link in navLinks"
          :key="link.name"
          :to="link.to"
          class="header__link"
          @click="closeMenu"
        >{{ link.label }}</RouterLink>
      </nav>

      <div class="header__actions">
        <select
          v-if="store.students.length > 1"
          :value="store.current"
          aria-label="Vybrat studenta"
          class="glass-btn header__select"
          @change="onSelectChange($event)"
        >
          <option v-for="s in store.students" :key="s" :value="s">{{ s }}</option>
        </select>
        <span v-else-if="store.current" class="header__student">{{ store.current }}</span>

        <NotificationBell class="header__bar-only" />
        <RouterLink to="/admin" class="glass-btn header__bar-only">Admin</RouterLink>

        <button
          class="header__burger"
          :class="{ 'header__burger--open': menuOpen }"
          :aria-expanded="menuOpen"
          aria-controls="header-drawer"
          :aria-label="menuOpen ? 'Zavřít menu' : 'Otevřít menu'"
          @click="menuOpen = !menuOpen"
        >
          <span></span><span></span><span></span>
        </button>
      </div>
    </div>

    <!-- Mobile drawer — sits below the bar in normal flow so it can never
         widen it, whatever the page content is. -->
    <nav
      v-show="menuOpen"
      id="header-drawer"
      class="header__drawer"
      aria-label="Mobilní navigace"
    >
      <RouterLink
        v-for="link in navLinks"
        :key="link.name"
        :to="link.to"
        class="header__link header__link--drawer"
        @click="closeMenu"
      >{{ link.label }}</RouterLink>

      <div class="header__drawer-meta">
        <NotificationBell />
        <RouterLink to="/admin" class="glass-btn" @click="closeMenu">Admin</RouterLink>
      </div>
    </nav>
  </header>
</template>

<style scoped>
.header {
  position: sticky;
  top: 0;
  z-index: 100;
  width: 100%;
  max-width: 100%;
  /* The header is a page-level band: its own content may never make it wider
     than the viewport, regardless of what the page below renders. */
  overflow-x: clip;
  background: var(--bg-secondary);
  background: color-mix(in srgb, var(--bg-secondary) 82%, transparent);
  backdrop-filter: blur(var(--blur));
  -webkit-backdrop-filter: blur(var(--blur));
  border-bottom: 1px solid var(--glass-border);
  padding-left: env(safe-area-inset-left);
  padding-right: env(safe-area-inset-right);
}

.header__bar {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  width: 100%;
  min-width: 0;
  min-height: var(--header-height);
  padding: var(--space-sm) var(--page-gutter);
}

.header__logo {
  flex: 0 1 auto;
  min-width: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  text-decoration: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.header__logo:hover { text-decoration: none; }

/* Desktop nav — allowed to scroll inside itself rather than push the bar */
.header__nav {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  gap: var(--space-xs);
  overflow-x: auto;
  overscroll-behavior-x: contain;
  scrollbar-width: none;
}
.header__nav::-webkit-scrollbar { display: none; }

.header__link {
  flex: 0 0 auto;
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  text-decoration: none;
  white-space: nowrap;
  transition: color var(--transition), background var(--transition);
}
.header__link:hover,
.header__link.router-link-exact-active {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.12);
  text-decoration: none;
}

.header__actions {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  min-width: 0;
  margin-left: auto;
}

.header__student {
  min-width: 0;
  max-width: 10rem;
  color: var(--text-secondary);
  font-size: var(--font-size-base);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header__select {
  min-width: 0;
  max-width: 12rem;
  padding: var(--space-xs) var(--space-sm);
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-primary);
  text-overflow: ellipsis;
  appearance: auto;
}
.header__select option { background: var(--bg-secondary); color: #fff; }

/* Hamburger — hidden on desktop, top-right corner on mobile */
.header__burger {
  display: none;
  flex: 0 0 auto;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  width: 40px;
  height: 40px;
  padding: 9px;
  background: rgba(255, 255, 255, 0.08);
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
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.header__burger--open span:nth-child(1) { transform: translateY(7px) rotate(45deg); }
.header__burger--open span:nth-child(2) { opacity: 0; }
.header__burger--open span:nth-child(3) { transform: translateY(-7px) rotate(-45deg); }

/* Drawer — hidden on desktop */
.header__drawer { display: none; }

/* ── Mobile / tablet ── */
@media (max-width: 900px) {
  .header__nav { display: none; }
  .header__bar-only { display: none; }
  .header__burger { display: flex; }

  .header__bar {
    gap: var(--space-sm);
    padding: var(--space-sm) var(--page-gutter);
  }

  .header__logo { font-size: var(--font-size-md); }

  /* Student switcher stays visible next to the burger, but is capped so a
     long name can never grow the bar. */
  .header__select,
  .header__student {
    flex: 0 1 auto;
    max-width: min(45vw, 11rem);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .header__select { min-height: 40px; font-size: var(--font-size-sm); }

  .header__drawer {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 100%;
    max-width: 100%;
    padding: var(--space-sm) var(--page-gutter) var(--space-md);
    border-top: 1px solid var(--glass-border);
    max-height: calc(100dvh - var(--header-height));
    overflow-y: auto;
    overscroll-behavior: contain;
  }

  .header__link--drawer {
    padding: var(--space-md);
    min-height: 44px;
    display: flex;
    align-items: center;
  }

  .header__drawer-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-sm);
    margin-top: var(--space-sm);
    padding-top: var(--space-md);
    border-top: 1px solid var(--glass-border);
  }
  .header__drawer-meta .glass-btn { min-height: 40px; display: inline-flex; align-items: center; }
}

/* Very narrow phones: drop the logo text before anything else can overflow */
@media (max-width: 359px) {
  .header__logo { display: none; }
  .header__select,
  .header__student { max-width: min(60vw, 12rem); }
}
</style>
