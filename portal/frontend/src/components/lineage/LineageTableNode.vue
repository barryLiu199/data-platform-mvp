<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps<{
  data: {
    tableName: string
    layer: 'source' | 'ods' | 'app'
    datasourceName?: string
    datasourceId?: number
    isCenter: boolean
    columns: Array<{ name: string; type: string }>
  }
}>()

const layerConfig = computed(() => {
  // 中心节点用主色，让用户一眼识别
  if (props.data.isCenter) {
    const sub = props.data.layer === 'app' ? _appSubLabel(props.data.tableName) : props.data.layer?.toUpperCase() || 'TABLE'
    return { label: sub, color: 'var(--color-primary)', bg: 'var(--color-primary-light)' }
  }
  switch (props.data.layer) {
    case 'source': return { label: 'SOURCE', color: 'var(--color-accent)', bg: 'var(--color-accent-light)' }
    case 'ods': return { label: 'ODS', color: 'var(--color-success)', bg: 'var(--color-success-light)' }
    case 'app': return { label: _appSubLabel(props.data.tableName), color: 'var(--color-warning)', bg: 'var(--color-warning-light)' }
    default: return { label: 'TABLE', color: 'var(--color-border-strong)', bg: 'var(--color-bg-elevated)' }
  }
})

function _appSubLabel(name: string): string {
  const lower = name.toLowerCase()
  if (lower.startsWith('dim')) return 'DIM'
  if (lower.startsWith('dw')) return 'DW'
  return 'ADS'
}
</script>

<template>
  <div
    class="lineage-node"
    :class="{ 'lineage-node--center': data.isCenter }"
    :style="{ borderColor: layerConfig.color }"
  >
    <Handle type="target" :position="Position.Left" class="lineage-handle" />

    <div class="lineage-node__header" :style="{ background: layerConfig.color }">
      <span class="lineage-node__badge">{{ layerConfig.label }}</span>
      <span class="lineage-node__name">{{ data.tableName }}</span>
    </div>

    <div class="lineage-node__body">
      <span v-if="data.datasourceName" class="lineage-node__ds">
        {{ data.datasourceName }}
      </span>
      <span v-if="data.columns.length" class="lineage-node__col-count">
        {{ data.columns.length }} 列
      </span>
    </div>

    <Handle type="source" :position="Position.Right" class="lineage-handle" />
  </div>
</template>

<style scoped>
.lineage-node {
  min-width: 180px;
  max-width: 260px;
  border: 2px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-card);
  overflow: hidden;
  transition: all 0.2s ease;
  cursor: pointer;
}
.lineage-node:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-1px);
}
.lineage-node--center {
  border-width: 3px;
  border-color: var(--color-primary) !important;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.2), var(--shadow-lg);
}
.lineage-node--center .lineage-node__badge::after {
  content: ' ★';
}

.lineage-node__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-3);
  color: var(--color-text-inverse);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
}
.lineage-node__badge {
  padding: 1px 6px;
  background: rgba(255, 255, 255, 0.25);
  border-radius: var(--radius-sm);
  font-size: 10px;
  letter-spacing: 0.5px;
}
.lineage-node__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lineage-node__body {
  padding: var(--space-2) var(--space-3);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}
.lineage-node__ds {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lineage-node__col-count {
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.lineage-handle {
  width: 8px;
  height: 8px;
  background: var(--color-border-strong);
  border: 2px solid var(--color-bg-surface);
}
</style>
