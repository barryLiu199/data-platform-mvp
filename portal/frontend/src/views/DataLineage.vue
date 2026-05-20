<template>
  <div class="page">
    <PageHeader title="数据血缘" description="选择 SQL 组件，追踪上下游表级数据流转">
      <template #actions>
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

      <a-tooltip content="字段级血缘（即将上线）">
        <a-switch v-model="fieldLevel" disabled size="small">
          <template #checked>字段</template>
          <template #unchecked>字段</template>
        </a-switch>
      </a-tooltip>
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
          <LineageTableNode :data="nodeProps.data" />
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { IconRefresh } from '@arco-design/web-vue/es/icon'
import { Message } from '@arco-design/web-vue'
import PageHeader from '../components/PageHeader.vue'
import LineageTableNode from '../components/lineage/LineageTableNode.vue'
import { getLineageEntities, getLineageGraph, refreshLineage } from '../api'

interface Entity { id: string | number; name: string; sub_type?: string; status?: string }
interface FlowNode { id: string; type: string; position: { x: number; y: number }; data: any }
interface FlowEdge { id: string; source: string; target: string; sourceHandle?: string; targetHandle?: string; label?: string; animated?: boolean; data?: any; style?: any }

// 控制栏状态
const entityId = ref('')
const depth = ref(2)
const fieldLevel = ref(false)
const entities = ref<Entity[]>([])
const entitiesLoading = ref(false)

// 画布状态
const flowNodes = ref<FlowNode[]>([])
const flowEdges = ref<FlowEdge[]>([])
const graphLoading = ref(false)
const refreshing = ref(false)
const queried = ref(false)
const graphStats = ref({ total_nodes: 0, total_edges: 0, upstream_depth: 0, downstream_depth: 0 })

// 高亮
const highlightedNodes = ref<Set<string>>(new Set())

async function loadEntities() {
  entitiesLoading.value = true
  try {
    const res: any = await getLineageEntities('component_sql')
    entities.value = res || []
  } catch { entities.value = [] }
  entitiesLoading.value = false
}

async function handleQuery() {
  if (!entityId.value) return

  graphLoading.value = true
  queried.value = true
  clearHighlight()

  try {
    const res: any = await getLineageGraph('component', entityId.value, {
      depth: depth.value,
      field_level: fieldLevel.value,
    })
    flowNodes.value = (res?.nodes || []).map((n: FlowNode) => ({
      ...n,
      data: { ...n.data, highlighted: false, dimmed: false },
    }))
    flowEdges.value = (res?.edges || []).map((e: FlowEdge) => ({
      ...e,
      style: {},
    }))
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
    Message.success(`血缘刷新完成：${res.edges_created} 条关系，耗时 ${res.duration_ms}ms`)
    // 重新加载组件列表（可能有新上线的组件）
    await loadEntities()
    if (entityId.value) await handleQuery()
  } catch { /* axios 拦截器会提示 */ }
  refreshing.value = false
}

// 全链路高亮
function onNodeClick({ node }: { node: FlowNode }) {
  const nodeId = node.id
  const reachable = new Set<string>()
  reachable.add(nodeId)

  // BFS 上游
  const upQueue = [nodeId]
  while (upQueue.length) {
    const cur = upQueue.shift()!
    for (const e of flowEdges.value) {
      if (e.target === cur && !reachable.has(e.source)) {
        reachable.add(e.source)
        upQueue.push(e.source)
      }
    }
  }
  // BFS 下游
  const downQueue = [nodeId]
  while (downQueue.length) {
    const cur = downQueue.shift()!
    for (const e of flowEdges.value) {
      if (e.source === cur && !reachable.has(e.target)) {
        reachable.add(e.target)
        downQueue.push(e.target)
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
    if (reachable.has(e.source) && reachable.has(e.target)) {
      reachableEdges.add(e.id)
    }
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
  if (!highlightedNodes.value.size) return
  highlightedNodes.value = new Set()
  flowNodes.value = flowNodes.value.map(n => ({
    ...n,
    data: { ...n.data, highlighted: false, dimmed: false },
    style: {},
  }))
  flowEdges.value = flowEdges.value.map(e => ({
    ...e,
    animated: false,
    style: {},
  }))
}

onMounted(() => {
  loadEntities()
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
