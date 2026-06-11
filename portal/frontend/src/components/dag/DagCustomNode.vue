<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import LangIcon from '../LangIcon.vue'
import { TYPE_GROUPS_WITH_DATAX } from '../../composables/useFileTree'

const props = defineProps<{
  data: {
    label: string
    type: string
    skip: boolean
    status?: string
    fail_strategy?: string
    retry_times?: number
    timeout?: number
  }
}>()

const hasBadges = computed(() =>
  props.data.fail_strategy === 'skip' || (props.data.retry_times || 0) > 0 || (props.data.timeout || 0) > 0
)

const typeGroup = computed(() => TYPE_GROUPS_WITH_DATAX.find(g => g.type === props.data.type))
const typeColor = computed(() => typeGroup.value?.color ?? '#6b7280')
const typeGradient = computed(() => typeGroup.value?.gradient ?? '#6b7280')
const typeLabel = computed(() => typeGroup.value?.label.split(' ')[0] ?? props.data.type)
</script>

<template>
  <div
    class="dag-node"
    :class="{ 'dag-node--skip': data.skip }"
    :style="{ borderColor: typeColor }"
  >
    <Handle type="target" :position="Position.Top" />
    <div class="dag-node__header" :style="{ background: typeGradient }">
      <LangIcon :type="data.type" :size="16" class="dag-node__lang-icon" />
      <span class="dag-node__type">{{ typeLabel }}</span>
    </div>
    <div class="dag-node__body">
      <span class="dag-node__label">{{ data.label }}</span>
      <span v-if="data.skip" class="dag-node__skip-badge">SKIP</span>
    </div>
    <div v-if="hasBadges" class="dag-node__badges">
      <span v-if="data.fail_strategy === 'skip'" class="dag-node__badge dag-node__badge--warn">失败跳过</span>
      <span v-if="(data.retry_times || 0) > 0" class="dag-node__badge">重试×{{ data.retry_times }}</span>
      <span v-if="(data.timeout || 0) > 0" class="dag-node__badge">{{ data.timeout }}min</span>
    </div>
    <Handle type="source" :position="Position.Bottom" />
  </div>
</template>

<style scoped>
.dag-node {
  min-width: 160px;
  border: 2px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  overflow: hidden;
  transition: all 0.2s;
}
.dag-node:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.12); }
.dag-node--skip { opacity: 0.5; }
.dag-node--skip .dag-node__label { text-decoration: line-through; }
.dag-node__header {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 10px; color: #fff; font-size: 11px; font-weight: 600;
}
.dag-node__lang-icon {
  border-radius: 3px;
  background: rgba(255,255,255,0.2) !important;
}
.dag-node__body { padding: 8px 10px; font-size: 13px; display: flex; align-items: center; gap: 6px; }
.dag-node__label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dag-node__skip-badge {
  font-size: 10px; background: #ef4444; color: #fff;
  padding: 1px 4px; border-radius: 3px; font-weight: 600;
}
.dag-node__badges {
  display: flex; flex-wrap: wrap; gap: 4px;
  padding: 0 10px 6px;
}
.dag-node__badge {
  font-size: 10px; background: #eff6ff; color: #2563eb;
  padding: 1px 5px; border-radius: 3px; font-weight: 500;
}
.dag-node__badge--warn { background: #fffbeb; color: #d97706; }
</style>
