<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { useStudentStore } from '@/stores/student'
import { useDashboardStore } from '@/stores/dashboard'
import TimetableWidget from '@/components/widgets/TimetableWidget.vue'
import SummaryWidget from '@/components/widgets/SummaryWidget.vue'
import KomensWidget from '@/components/widgets/KomensWidget.vue'
import MarksWidget from '@/components/widgets/MarksWidget.vue'
import PrepareWidget from '@/components/widgets/PrepareWidget.vue'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'

const studentStore = useStudentStore()
const dashboard = useDashboardStore()

function reload() {
  if (studentStore.current) dashboard.load(studentStore.current)
}

onMounted(reload)
watch(() => studentStore.current, reload)
</script>

<template>
  <div class="dashboard">
    <div class="dashboard__bg"></div>
    <div class="dashboard__content">
      <LoadingSpinner v-if="dashboard.loading && !dashboard.data" />
      <p v-else-if="dashboard.error" class="error">{{ dashboard.error }}</p>
      <div v-else-if="dashboard.data" class="grid">
        <TimetableWidget :data="dashboard.data.today_timetable" :extra-subjects="dashboard.data.extra_subjects" />
        <SummaryWidget :last="dashboard.data.summary_last" :current="dashboard.data.summary_current" :next="dashboard.data.summary_next" />
        <PrepareWidget :data="dashboard.data.prepare_today" title="Dnes" />
        <PrepareWidget :data="dashboard.data.prepare_tomorrow" title="Zítra" />
        <KomensWidget :data="dashboard.data.komens" />
        <MarksWidget :data="dashboard.data.marks" />
      </div>
      <p v-else class="empty">Vyberte studenta pro zobrazení přehledu</p>
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  position: relative;
  min-height: calc(100vh - 4rem);
}

.dashboard__bg {
  position: fixed;
  inset: 0;
  z-index: -1;
  background:
    radial-gradient(ellipse at 20% 50%, rgba(99, 102, 241, 0.08) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 20%, rgba(139, 92, 246, 0.06) 0%, transparent 50%),
    radial-gradient(ellipse at 50% 80%, rgba(59, 130, 246, 0.05) 0%, transparent 50%),
    linear-gradient(135deg, var(--bg-dashboard) 0%, var(--bg-primary) 50%, var(--bg-secondary) 100%);
}

.dashboard__content {
  position: relative;
  z-index: 1;
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-lg);
}
@media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
.error { color: var(--error); font-size: var(--font-size-base); }
.empty { color: var(--text-muted); text-align: center; padding: 3rem; font-size: var(--font-size-base); }
</style>
