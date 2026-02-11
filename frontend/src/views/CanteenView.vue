<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getCanteen } from '@/api/client'
import type { CanteenData } from '@/types'
import GlassCard from '@/components/ui/GlassCard.vue'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'

const data = ref<CanteenData | null>(null)
const loading = ref(false)

const today = computed(() => new Date().toISOString().slice(0, 10))

async function load() {
  loading.value = true
  try {
    data.value = await getCanteen()
  } finally {
    loading.value = false
  }
}

function mealIcon(druh: string): string {
  const icons: Record<string, string> = {
    PR: 'snack',
    PO: 'soup',
    OB: 'lunch',
    DO: 'drink',
    SV: 'snack',
    OD: 'diet',
  }
  return icons[druh] || ''
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="page-title">Jídelníček</h2>

    <LoadingSpinner v-if="loading && !data" />

    <p v-else-if="!data || !data.days.length" class="empty">
      Jídelníček není k dispozici
    </p>

    <div v-else class="days">
      <GlassCard
        v-for="day in data.days"
        :key="day.date"
        class="day-card"
        :class="{ 'day-card--today': day.date === today }"
      >
        <div class="day-header">
          <span class="day-name">{{ day.day_name }}</span>
          <span class="day-date">{{ day.date_label }}</span>
          <span v-if="day.date === today" class="badge badge--accent">dnes</span>
        </div>

        <div class="meals">
          <div
            v-for="(meal, i) in day.meals"
            :key="i"
            class="meal"
            :class="`meal--${mealIcon(meal.druh)}`"
          >
            <span class="meal__type">{{ meal.druh_popis }}</span>
            <span class="meal__name">{{ meal.nazev }}</span>
            <div v-if="meal.alergeny.length" class="meal__allergens">
              <span
                v-for="a in meal.alergeny"
                :key="a.code"
                class="allergen"
                :title="a.name"
              >{{ a.code }}</span>
            </div>
          </div>
        </div>
      </GlassCard>
    </div>
  </div>
</template>

<style scoped>
.days {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.day-card--today {
  border: 1px solid rgba(99, 102, 241, 0.3);
}

.day-header {
  display: flex;
  align-items: baseline;
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}

.day-name {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.day-date {
  font-size: var(--font-size-sm);
  color: var(--text-muted);
}

.meals {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.meal {
  display: grid;
  grid-template-columns: 7rem 1fr auto;
  gap: var(--space-sm);
  align-items: baseline;
  padding: var(--space-sm) 0;
  border-bottom: var(--border-subtle);
}
.meal:last-child { border-bottom: none; }

.meal__type {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  font-weight: var(--font-weight-medium);
}

.meal__name {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}

.meal__allergens {
  display: flex;
  gap: 3px;
  flex-wrap: wrap;
}

.allergen {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.06);
  padding: 1px 5px;
  border-radius: var(--radius-xs);
  white-space: nowrap;
}

.empty {
  color: var(--text-muted);
  font-size: var(--font-size-base);
}

@media (max-width: 768px) {
  .meal {
    grid-template-columns: 1fr;
    gap: 2px;
  }
  .meal__type {
    font-size: var(--font-size-xs);
    color: var(--text-muted);
  }
  .meal__allergens {
    margin-top: 2px;
  }
}
</style>
