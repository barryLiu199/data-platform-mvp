<template>
  <div class="page">
    <PageHeader title="数据血缘" description="选择 SQL 组件，追踪上下游表级与字段级数据流转">
      <template #actions>
        <a-badge :count="failureCount" :max-count="99" v-if="failureCount > 0">
          <a-button @click="failureDrawer = true">
            <template #icon><icon-exclamation-circle /></template>
            未解析
          </a-button>
        </a-badge>
        <a-button v-else @click="failureDrawer = true">
          <template #icon><icon-exclamation-circle /></template>
          未解析
        </a-button>
        <a-button @click="openManual">手工补登</a-button>
        <a-button @click="handleRefresh" :loading="refreshing">
          <template #icon><icon-refresh /></template>
          刷新血缘
        </a-button>
      </template>
    </PageHeader>

    <!-- 控制栏 -->
    <div class="glass-card control-bar">
      <a-select
        v-model="entityId"
        placeholder="选择 SQL 组件"
        style="width: 280px"
        :loading="entitiesLoading"
        allow-search
        @change="handleQuery"
      >
        <a-option v-for="e in entities" :key="e.id" :value="String(e.id)">
          {{ e.name }}
        </a-option>
      </a-select>

      <a-select v-model="depth" placeholder="展开深度" style="width: 120px" @change="handleQuery">
        <a-option :value="1">1 层</a-option>
        <a-option :value="2">2 层</a-option>
        <a-option :value="3">3 层</a-option>
      </a-select>

      <div v-if="isFieldView" class="field-view-tag">
        <a-tag color="blue" size="medium">
          字段视图：{{ selectedColumn?.table }}.{{ selectedColumn?.column }}
        </a-tag>
        <a-button size="small" @click="exitColumnView">
          <template #icon><icon-arrow-left /></template>
          返回表视图
        </a-button>
      </div>
      <span v-else class="text-muted" style="font-size:12px">
        💡 点击节点字段进入字段血缘视图
      </span>
    </div>

    <!-- 画布 -->
    <div class="glass-card canvas-wrapper" v-if="flowNodes.length">
      <VueFlow
        v-model:nodes="flowNodes"
        v-model:edges="flowEdges"
        :nodes-connectable="false"
        :edges-updatable="false"
        :nodes-draggable="true"
        fit-view-on-init
        class="lineage-canvas"
        @node-click="onNodeClick"
        @pane-click="clearHighlight"
      >
        <template #node-lineage-table="nodeProps">
          <LineageTableNode :data="nodeProps.data" @select-column="onSelectColumn" />
        </template>
        <Background />
        <Controls :show-fit-view="true" :show-interactive="false" />
      </VueFlow>

      <!-- 统计 -->
      <div class="canvas-stats">
        <a-tag size="small" color="blue">{{ graphStats.total_nodes }} 表</a-tag>
        <a-tag size="small" color="cyan">{{ graphStats.total_edges }} 关系</a-tag>
        <a-tag size="small" color="green">{{ graphStats.upstream_depth }} 层上游</a-tag>
        <a-tag size="small" color="orange">{{ graphStats.downstream_depth }} 层下游</a-tag>
      </div>
    </div>

    <!-- 空状态 -->
    <div class="glass-card empty-card" v-else-if="!graphLoading && queried">
      <div class="empty-state">
        <p>暂无血缘数据</p>
        <p class="text-muted">该组件尚未解析到表级血缘关系，请先点击"刷新血缘"</p>
      </div>
    </div>

    <!-- 初始引导 -->
    <div class="glass-card empty-card" v-else-if="!graphLoading && !queried">
      <div class="empty-state">
        <p>选择一个 SQL 组件开始探索血缘</p>
        <p class="text-muted">从上方下拉框选择组件，自动展示上下游数据流转关系</p>
      </div>
    </div>

    <!-- 加载中 -->
    <div class="glass-card loading-card" v-else>
      <a-spin dot /><span class="text-muted" style="margin-left:8px">正在构建血缘图...</span>
    </div>

    <ParseFailureDrawer
      v-model:visible="failureDrawer"
      @open-manual="openManual"
      @changed="loadFailureCount"
    />
    <ManualLineageModal
      v-model:visible="manualModal"
      @created="onManualCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { IconRefresh, IconArrowLeft, IconExclamationCircle } from '@arco-design/web-vue/es/icon'
import { Message } from '@arco-design/web-vue'
import PageHeader from '../components/PageHeader.vue'
import LineageTableNode from '../components/lineage/LineageTableNode.vue'
import ParseFailureDrawer from '../components/lineage/ParseFailureDrawer.vue'
import ManualLineageModal from '../components/lineage/ManualLineageModal.vue'
import {
  getLineageEntities, getLineageGraph, refreshLineage,
  refreshColumnLineage, getColumnLineageGraph, getColumnParseFailures,
} from '../api'

interface Entity { id: string | number; name: string; sub_type?: string; status?: string }
interface FlowNode { id: string; type: string; position: { x: number; y: number }; data: any; style?: any }
interface FlowEdge { id: string; source: string; target: string; sourceHandle?: string; targetHandle?: string; label?: string; animated?: boolean; data?: any; style?: any }

const entityId = ref('')
const depth = ref(2)
const entities = ref<Entity[]>([])
const entitiesLoading = ref(false)

const flowNodes = ref<FlowNode[]>([])
const flowEdges = ref<FlowEdge[]>([])
const graphLoading = ref(false)
const refreshing = ref(false)
const queried = ref(false)
const graphStats = ref({ total_nodes: 0, total_edges: 0, upstream_depth: 0, downstream_depth: 0 })

const highlightedNodes = ref<Set<string>>(new Set())

// 字段视图状态
const selectedColumn = ref<{ table: string; column: string } | null>(null)
const columnPathTables = ref<Set<string>>(new Set())
const columnPathEdgeKeys = ref<Set<string>>(new Set())  // 'srcTable.col→tgtTable.col'

// 解析失败 + 手工补登
const failureDrawer = ref(false)
const manualModal = ref(false)
const failureCount = ref(0)

const isFieldView = computed(() => selectedColumn.value !== null)

async function loadEntities() {
  entitiesLoading.value = true
  try {
    const res: any = await getLineageEntities('component_sql')
    entities.value = res || []
  } catch { entities.value = [] }
  entitiesLoading.value = false
}

async function loadFailureCount() {
  try {
    const res = await getColumnParseFailures({ page: 1, page_size: 1 })
    failureCount.value = res?.total || 0
  } catch { failureCount.value = 0 }
}

async function handleQuery() {
  if (!entityId.value) return
  graphLoading.value = true
  queried.value = true
  exitColumnView()
  clearHighlight()

  try {
    const res: any = await getLineageGraph('component', entityId.value, { depth: depth.value })
    flowNodes.value = (res?.nodes || []).map((n: FlowNode) => ({
      ...n,
      data: { ...n.data, highlighted: false, dimmed: false },
    }))
    flowEdges.value = (res?.edges || []).map((e: FlowEdge) => ({ ...e, style: {} }))
    graphStats.value = res?.stats || { total_nodes: 0, total_edges: 0, upstream_depth: 0, downstream_depth: 0 }
  } catch {
    flowNodes.value = []
    flowEdges.value = []
  }
  graphLoading.value = false
}

async function handleRefresh() {
  refreshing.value = true
  try {
    const res: any = await refreshLineage()
    Message.success(`表级血缘刷新完成：${res.edges_created} 条关系，耗时 ${res.duration_ms}ms`)
    // 触发字段血缘前台刷新（同步等待结果）
    try {
      const cstats = await refreshColumnLineage()
      Message.success(`字段血缘：sync ${cstats.sync_task} + sql ${cstats.component_sql} + datax ${cstats.component_datax}（失败 ${cstats.failed}）`)
    } catch {
      Message.warning('字段血缘刷新失败，但表级血缘已更新')
    }
    await Promise.all([loadEntities(), loadFailureCount()])
    if (entityId.value) await handleQuery()
  } catch { /* axios 拦截器会提示 */ }
  refreshing.value = false
}

function _tableNameFromNode(nodeId: string): string {
  // node.id 形如 'table::ods_user'
  return nodeId.startsWith('table::') ? nodeId.slice(7) : nodeId
}

async function onSelectColumn(payload: { table: string; column: string }) {
  const table = payload.table.toLowerCase()
  const column = payload.column.toLowerCase()
  selectedColumn.value = { table, column }

  try {
    const graph = await getColumnLineageGraph(table, column, { depth: 3, direction: 'both' })
    const tables = new Set<string>()
    for (const n of graph.nodes) tables.add(n.table)
    const edgeKeys = new Set<string>()
    for (const e of graph.edges) {
      const sn = graph.nodes.find(n => n.id === e.source)
      const tn = graph.nodes.find(n => n.id === e.target)
      if (sn && tn) edgeKeys.add(`${sn.table}|${tn.table}`)
    }
    columnPathTables.value = tables
    columnPathEdgeKeys.value = edgeKeys
    _applyColumnView()
  } catch (e) {
    Message.error('获取字段血缘失败')
    exitColumnView()
  }
}

function _applyColumnView() {
  const col = selectedColumn.value
  if (!col) return
  flowNodes.value = flowNodes.value.map(n => {
    const tname = _tableNameFromNode(n.id)
    const inPath = columnPathTables.value.has(tname)
    return {
      ...n,
      data: {
        ...n.data,
        selectedColumn: tname === col.table ? col.column : '',
        inColumnPath: inPath,
      },
      style: inPath ? {} : { opacity: 0.3 },
    }
  })
  flowEdges.value = flowEdges.value.map(e => {
    const srcTable = _tableNameFromNode(e.source)
    const tgtTable = _tableNameFromNode(e.target)
    const inPath = columnPathEdgeKeys.value.has(`${srcTable}|${tgtTable}`)
    return {
      ...e,
      animated: inPath,
      style: inPath
        ? { stroke: 'var(--color-primary)', strokeWidth: 2 }
        : { opacity: 0.15 },
    }
  })
}

function exitColumnView() {
  if (!selectedColumn.value) return
  selectedColumn.value = null
  columnPathTables.value = new Set()
  columnPathEdgeKeys.value = new Set()
  flowNodes.value = flowNodes.value.map(n => ({
    ...n,
    data: { ...n.data, selectedColumn: '', inColumnPath: false, highlighted: false, dimmed: false },
    style: {},
  }))
  flowEdges.value = flowEdges.value.map(e => ({ ...e, animated: false, style: {} }))
}

function onNodeClick({ node }: { node: FlowNode }) {
  if (isFieldView.value) return
  const nodeId = node.id
  const reachable = new Set<string>()
  reachable.add(nodeId)
  const upQueue = [nodeId]
  while (upQueue.length) {
    const cur = upQueue.shift()!
    for (const e of flowEdges.value) {
      if (e.target === cur && !reachable.has(e.source)) {
        reachable.add(e.source); upQueue.push(e.source)
      }
    }
  }
  const downQueue = [nodeId]
  while (downQueue.length) {
    const cur = downQueue.shift()!
    for (const e of flowEdges.value) {
      if (e.source === cur && !reachable.has(e.target)) {
        reachable.add(e.target); downQueue.push(e.target)
      }
    }
  }
  highlightedNodes.value = reachable
  flowNodes.value = flowNodes.value.map(n => ({
    ...n,
    data: { ...n.data, highlighted: reachable.has(n.id), dimmed: !reachable.has(n.id) },
    style: reachable.has(n.id) ? {} : { opacity: 0.3 },
  }))
  const reachableEdges = new Set<string>()
  for (const e of flowEdges.value) {
    if (reachable.has(e.source) && reachable.has(e.target)) reachableEdges.add(e.id)
  }
  flowEdges.value = flowEdges.value.map(e => ({
    ...e,
    animated: reachableEdges.has(e.id),
    style: reachableEdges.has(e.id)
      ? { stroke: 'var(--color-primary)', strokeWidth: 2 }
      : { opacity: 0.15 },
  }))
}

function clearHighlight() {
  if (isFieldView.value) return
  if (!highlightedNodes.value.size) return
  highlightedNodes.value = new Set()
  flowNodes.value = flowNodes.value.map(n => ({
    ...n,
    data: { ...n.data, highlighted: false, dimmed: false },
    style: {},
  }))
  flowEdges.value = flowEdges.value.map(e => ({ ...e, animated: false, style: {} }))
}

function openManual() { manualModal.value = true }
function onManualCreated() {
  manualModal.value = false
  Message.success('已添加手工补登字段血缘')
  if (entityId.value) handleQuery()
}

const route = useRoute()

async function tryConsumeFocusQuery() {
  const focus = route.query.focus
  if (typeof focus !== 'string' || !focus.includes('.')) return
  const [tableRaw, ...rest] = focus.split('.')
  const colRaw = rest.join('.')
  const table = tableRaw.toLowerCase()
  const column = colRaw.toLowerCase()
  if (!table || !column) return

  // 找一个包含该表的组件作为入口（按图含 table 节点匹配）
  for (const e of entities.value) {
    try {
      const res: any = await getLineageGraph('component', String(e.id), { depth: 2 })
      const nodes = res?.nodes || []
      const hit = nodes.some((n: any) => {
        const t = (n.data?.tableName || n.id || '').toString().toLowerCase()
        return t === table || t.endsWith('::' + table)
      })
      if (hit) {
        entityId.value = String(e.id)
        await handleQuery()
        await onSelectColumn({ table, column })
        return
      }
    } catch { /* try next entity */ }
  }
  Message.warning(`未找到包含 ${table}.${column} 的组件，请手动选择 SQL 组件`)
}

onMounted(async () => {
  await loadEntities()
  loadFailureCount()
  await tryConsumeFocusQuery()
})
</script>

<style scoped>
.page { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.control-bar {
  padding: var(--space-3) var(--space-4);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.canvas-wrapper {
  padding: 0;
  position: relative;
  height: calc(100vh - 260px);
  min-height: 400px;
}
.lineage-canvas {
  width: 100%;
  height: 100%;
}

.canvas-stats {
  position: absolute;
  bottom: var(--space-3);
  left: var(--space-3);
  display: flex;
  gap: var(--space-1);
  z-index: 5;
}

.empty-card, .loading-card { padding: 80px 0; text-align: center; }
.text-muted { color: var(--color-text-tertiary); }
.empty-state { padding: var(--space-10) 0; text-align: center; }
.empty-state p { margin: var(--space-2) 0; }

.field-view-tag {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-left: auto;
}
</style>

<style>
@import '@vue-flow/core/dist/style.css';
@import '@vue-flow/core/dist/theme-default.css';
@import '@vue-flow/controls/dist/style.css';

.lineage-canvas .vue-flow__edge-path {
  stroke: var(--color-border-strong);
  stroke-width: 1.5;
}
.lineage-canvas .vue-flow__edge-textbg {
  fill: var(--color-bg-surface);
}
.lineage-canvas .vue-flow__edge-text {
  font-size: 11px;
  fill: var(--color-text-secondary);
}
</style>
