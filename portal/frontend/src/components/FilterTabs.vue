<template>
  <div class="filter-tabs">
    <div
      v-for="tab in tabs"
      :key="tab.value"
      class="tab-item"
      :class="{ active: modelValue === tab.value }"
      @click="$emit('update:modelValue', tab.value)"
    >
      {{ tab.label }}
      <span v-if="tab.count != null" class="tab-count">{{ tab.count }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface FilterTab {
  label: string
  value: string
  count?: number
}

defineProps<{
  tabs: FilterTab[]
  modelValue: string
}>()

defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<style scoped>
.filter-tabs {
  display: flex;
  gap: var(--space-1);
  margin-bottom: var(--space-3);
}
.tab-item {
  padding: var(--space-1) var(--space-3);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
}
.tab-item:hover {
  color: var(--color-primary);
  background: var(--color-bg-elevated);
}
.tab-item.active {
  color: var(--color-primary);
  background: var(--color-primary-light);
  font-weight: var(--font-weight-medium);
}
.tab-count {
  margin-left: var(--space-1);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
.tab-item.active .tab-count {
  color: var(--color-primary);
}
</style>
