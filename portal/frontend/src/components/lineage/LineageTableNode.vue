<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { IconCaretDown, IconCaretRight } from '@arco-design/web-vue/es/icon'
import ColumnRow from './ColumnRow.vue'
import { getMetadataColumns, getColumnsWithLineage } from '../../api'

const props = defineProps<{
  data: {
    tableName: string
    layer: 'source' | 'ods' | 'app'
    datasourceName?: string
    datasourceId?: number
    isCenter: boolean
    columns: Array<{ name: string; type: string }>
    /** 字段视图：当前选中字段（高亮用） */
    selectedColumn?: string
    /** 字段视图：当前节点是否参与字段链路 */
    inColumnPath?: boolean
  }
}>()

const emit = defineEmits<{
  (e: 'select-column', payload: { table: string; column: string }): void
}>()

const expanded = ref(false)
const loadedColumns = ref<Array<{ name: string; type: string }>>([])
const lineageColumns = ref<Set<string>>(new Set())
const loading = ref(false)

const displayColumns = computed(() => {
  if (loadedColumns.value.length) return loadedColumns.value
  return props.data.columns || []
})

async function toggle() {
  expanded.value = !expanded.value
  if (expanded.value && !loadedColumns.value.length) {
    await loadColumns()
  }
}

async function loadColumns() {
  if (!props.data.datasourceId) return
  loading.value = true
  try {
    const [cols, hint] = await Promise.all([
      getMetadataColumns(props.data.datasourceId, props.data.tableName) as Promise<any>,
      getColumnsWithLineage(props.data.tableName).catch(() => ({ columns_with_lineage: [] as string[] })),
    ])
    const arr = Array.isArray(cols) ? cols : (cols?.items || [])
    loadedColumns.value = arr.map((c: any) => ({
      name: c.name || c.column_name || c.COLUMN_NAME,
      type: c.type || c.data_type || c.DATA_TYPE || '',
    })).filter((c: any) => c.name)
    lineageColumns.value = new Set(hint.columns_with_lineage || [])
  } catch (e) {
    // 静默失败 — 不影响节点显示
  } finally {
    loading.value = false
  }
}

watch(() => props.data.selectedColumn, (col) => {
  if (col && !expanded.value) {
    expanded.value = true
    if (!loadedColumns.value.length) loadColumns()
  }
})

const layerConfig = computed(() => {
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

function onColumnClick(col: string) {
  emit('select-column', { table: props.data.tableName, column: col })
}
</script>

<template>
  <div
    class="lineage-node"
    :class="{
      'lineage-node--center': data.isCenter,
      'lineage-node--in-path': data.inColumnPath,
      'lineage-node--dimmed': data.selectedColumn && !data.inColumnPath,
    }"
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
    </div>

    <div class="lineage-node__toggle" @click.stop="toggle">
      <icon-caret-down v-if="expanded" />
      <icon-caret-right v-else />
      <span>{{ displayColumns.length || 0 }} 列</span>
      <span v-if="loading" class="lineage-node__loading">加载中…</span>
    </div>

    <div v-if="expanded" class="lineage-node__cols">
      <column-row
        v-for="col in displayColumns"
        :key="col.name"
        :name="col.name"
        :type="col.type"
        :has-lineage="lineageColumns.has(col.name.toLowerCase())"
        :selected="data.selectedColumn === col.name.toLowerCase()"
        @click="onColumnClick(col.name)"
      />
      <div v-if="!displayColumns.length && !loading" class="lineage-node__empty">
        无字段
      </div>
    </div>

    <Handle type="source" :position="Position.Right" class="lineage-handle" />
  </div>
</template>

<style scoped>
.lineage-node {
  min-width: 200px;
  max-width: 280px;
  border: 2px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-card);
  overflow: hidden;
  transition: all 0.2s ease;
}
.lineage-node:hover { box-shadow: var(--shadow-lg); }
.lineage-node--center {
  border-width: 3px;
  border-color: var(--color-primary) !important;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.2), var(--shadow-lg);
}
.lineage-node--center .lineage-node__badge::after { content: ' ★'; }
.lineage-node--in-path {
  box-shadow: 0 0 0 2px var(--color-primary), var(--shadow-lg);
}
.lineage-node--dimmed { opacity: 0.45; }

.lineage-node__header {
  display: flex; align-items: center; gap: var(--space-2);
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
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.lineage-node__body {
  padding: var(--space-1) var(--space-3);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}
.lineage-node__ds {
  display: block;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.lineage-node__toggle {
  display: flex; align-items: center; gap: var(--space-1);
  padding: 4px var(--space-3);
  border-top: 1px solid var(--color-border);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
  user-select: none;
  background: var(--color-bg-elevated);
}
.lineage-node__toggle:hover { color: var(--color-primary); }
.lineage-node__loading { margin-left: auto; color: var(--color-text-tertiary); }

.lineage-node__cols {
  max-height: 280px;
  overflow-y: auto;
  background: var(--color-bg-surface);
  border-top: 1px solid var(--color-border);
}
.lineage-node__empty {
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  text-align: center;
}

.lineage-handle {
  width: 8px; height: 8px;
  background: var(--color-border-strong);
  border: 2px solid var(--color-bg-surface);
}
</style>
