<template>
  <div class="empty-state" :style="compact ? { padding: 'var(--space-4) 0' } : {}">
    <a-empty :description="description">
      <template v-if="$slots.default" #default>
        <slot />
      </template>
    </a-empty>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  description?: string
  compact?: boolean
}>(), {
  description: '暂无数据',
  compact: false,
})
</script>

<style scoped>
.empty-state {
  padding: var(--space-10) 0;
  text-align: center;
}
</style>
