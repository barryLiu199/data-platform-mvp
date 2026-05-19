<template>
  <a-tag :color="tagColor" size="small">
    <template v-if="dot">
      <span class="status-dot" :style="{ background: dotColor }" />
    </template>
    {{ label }}
  </a-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  getExecutionStatus,
  getLifecycleStatus,
  getSyncTaskStatus,
} from '../constants/status'

const props = withDefaults(defineProps<{
  status: string
  type?: 'execution' | 'lifecycle' | 'sync'
  dot?: boolean
}>(), {
  type: 'lifecycle',
  dot: false,
})

const resolved = computed(() => {
  switch (props.type) {
    case 'execution': return { ...getExecutionStatus(props.status), tagColor: undefined }
    case 'sync': return getSyncTaskStatus(props.status)
    default: return getLifecycleStatus(props.status)
  }
})

const tagColor = computed(() => {
  if (props.type === 'execution') {
    // 执行状态没有 Arco tag color 名，用自定义样式
    return undefined
  }
  return resolved.value.tagColor ?? 'gray'
})

const dotColor = computed(() => resolved.value.color)
const label = computed(() => resolved.value.label)
</script>

<style scoped>
.status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: var(--space-1);
  vertical-align: middle;
}
</style>
