<script setup lang="ts">
defineProps<{
  name: string
  type?: string
  hasLineage?: boolean
  selected?: boolean
}>()

defineEmits<{
  (e: 'click'): void
}>()
</script>

<template>
  <div
    class="col-row"
    :class="{ 'col-row--selected': selected, 'col-row--has-lineage': hasLineage }"
    @click.stop="$emit('click')"
  >
    <span class="col-row__dot" :class="{ active: hasLineage }" />
    <span class="col-row__name" :title="name">{{ name }}</span>
    <span v-if="type" class="col-row__type" :title="type">{{ type }}</span>
  </div>
</template>

<style scoped>
.col-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 3px var(--space-3);
  font-size: var(--font-size-xs);
  color: var(--color-text-primary);
  cursor: pointer;
  transition: background 0.15s ease;
  border-bottom: 1px solid var(--color-border);
}
.col-row:last-child { border-bottom: none; }
.col-row:hover { background: var(--color-bg-elevated); }
.col-row--selected {
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-weight: var(--font-weight-semibold);
}
.col-row--has-lineage:not(.col-row--selected) .col-row__name {
  color: var(--color-text-primary);
}
.col-row:not(.col-row--has-lineage):not(.col-row--selected) .col-row__name {
  color: var(--color-text-tertiary);
}

.col-row__dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--color-border-strong);
  flex-shrink: 0;
}
.col-row__dot.active { background: var(--color-primary); }

.col-row__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.col-row__type {
  color: var(--color-text-tertiary);
  font-size: 10px;
  text-transform: uppercase;
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
