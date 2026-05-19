<template>
  <div class="glass-card page-header">
    <div class="page-header__left">
      <h3 class="page-title">{{ title }}</h3>
      <p v-if="description" class="page-desc">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="page-header__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-5) var(--space-6);
  margin-bottom: var(--space-5);
}
.page-title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}
.page-desc {
  margin: var(--space-1) 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}
.page-header__actions {
  flex-shrink: 0;
}
</style>
