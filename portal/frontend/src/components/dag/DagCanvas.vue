<script setup lang="ts">
import { ref, watch } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import DagCustomNode from './DagCustomNode.vue'
import DagContextMenu from './DagContextMenu.vue'
import NodeConfigModal, { type NodeConfig } from './NodeConfigModal.vue'

interface DagNode {
  id: string; component_id: number; type?: string; name: string
  position: { x: number; y: number }; skip: boolean
  fail_strategy?: 'end' | 'skip'
  retry_times?: number
  retry_interval?: number
  timeout?: number
  priority?: string
}
interface DagEdge { id: string; source: string; target: string }

const props = defineProps<{ nodes: DagNode[]; edges: DagEdge[] }>()
const emit = defineEmits<{
  (e: 'update', dag: { nodes: DagNode[]; edges: DagEdge[] }): void
}>()

const contextMenu = ref<InstanceType<typeof DagContextMenu>>()
const configModal = ref<InstanceType<typeof NodeConfigModal>>()
let nodeCounter = ref(0)

const { onConnect, addEdges, onNodeDragStop, getNodes, getEdges, addNodes, removeNodes, removeEdges } = useVueFlow()

// 初始化节点和边
const flowNodes = ref<any[]>([])
const flowEdges = ref<any[]>([])

watch(() => [props.nodes, props.edges], () => {
  flowNodes.value = props.nodes.map(n => ({
    id: n.id, type: 'component-node', position: n.position,
    data: {
      label: n.name, type: n.type || 'sql', skip: n.skip, component_id: n.component_id,
      fail_strategy: n.fail_strategy || 'end',
      retry_times: n.retry_times || 0,
      retry_interval: n.retry_interval || 1,
      timeout: n.timeout || 0,
      priority: n.priority || 'MEDIUM',
    },
  }))
  flowEdges.value = props.edges.map(e => ({
    id: e.id, source: e.source, target: e.target, animated: true,
  }))
  nodeCounter.value = props.nodes.length
}, { immediate: true })

function getNodeType(compId: number): string {
  const node = props.nodes.find(n => n.component_id === compId)
  return (node as any)?.type || 'sql'
}

// 连线事件
onConnect((params) => {
  if (params.source === params.target) return
  const exists = flowEdges.value.some(e => e.source === params.source && e.target === params.target)
  if (exists) return
  const newEdge = { id: `edge-${Date.now()}`, source: params.source, target: params.target, animated: true }
  flowEdges.value = [...flowEdges.value, newEdge]
  emitUpdate()
})

onNodeDragStop(() => { emitUpdate() })

// 拖拽添加节点
function onDrop(event: DragEvent) {
  const data = event.dataTransfer?.getData('application/dag-component')
  if (!data) return
  const comp = JSON.parse(data)
  const bounds = (event.target as HTMLElement).closest('.vue-flow')?.getBoundingClientRect()
  if (!bounds) return
  const position = { x: event.clientX - bounds.left - 80, y: event.clientY - bounds.top - 20 }
  nodeCounter.value++
  const newNode = {
    id: `node-${Date.now()}`, type: 'component-node', position,
    data: {
      label: comp.name, type: comp.type, skip: false, component_id: comp.id,
      fail_strategy: 'end', retry_times: 0, retry_interval: 1, timeout: 0, priority: 'MEDIUM',
    },
  }
  flowNodes.value = [...flowNodes.value, newNode]
  emitUpdate()
}

function onDragOver(event: DragEvent) { event.preventDefault(); event.dataTransfer!.dropEffect = 'move' }

// 右键菜单
function onNodeContextMenu(event: { event: MouseEvent; node: any }) {
  const skip = event.node.data?.skip || false
  contextMenu.value?.show(event.event, event.node.id, skip)
}

// 双击节点打开配置弹窗
function onNodeDoubleClick(event: { event: MouseEvent; node: any }) {
  configModal.value?.open(event.node.id, event.node.data || {})
}

function saveNodeConfig(id: string, cfg: NodeConfig) {
  flowNodes.value = flowNodes.value.map(n => n.id === id ? { ...n, data: { ...n.data, ...cfg } } : n)
  emitUpdate()
}

function skipNode(id: string) {
  flowNodes.value = flowNodes.value.map(n => n.id === id ? { ...n, data: { ...n.data, skip: true } } : n)
  emitUpdate()
}
function unskipNode(id: string) {
  flowNodes.value = flowNodes.value.map(n => n.id === id ? { ...n, data: { ...n.data, skip: false } } : n)
  emitUpdate()
}
function deleteNode(id: string) {
  flowNodes.value = flowNodes.value.filter(n => n.id !== id)
  flowEdges.value = flowEdges.value.filter(e => e.source !== id && e.target !== id)
  emitUpdate()
}

function emitUpdate() {
  const nodes = flowNodes.value.map((n: any) => ({
    id: n.id, component_id: n.data.component_id, name: n.data.label,
    type: n.data.type, position: n.position, skip: n.data.skip || false,
    fail_strategy: n.data.fail_strategy || 'end',
    retry_times: n.data.retry_times || 0,
    retry_interval: n.data.retry_interval || 1,
    timeout: n.data.timeout || 0,
    priority: n.data.priority || 'MEDIUM',
  }))
  const edges = flowEdges.value.map((e: any) => ({ id: e.id, source: e.source, target: e.target }))
  emit('update', { nodes, edges })
}

// 自动布局（简单拓扑排序 + 网格）
function autoLayout() {
  const sorted = topologicalSort()
  sorted.forEach((id, i) => {
    const node = flowNodes.value.find((n: any) => n.id === id)
    if (node) node.position = { x: 200 + (i % 4) * 220, y: 100 + Math.floor(i / 4) * 150 }
  })
  flowNodes.value = [...flowNodes.value]
  emitUpdate()
}

function topologicalSort(): string[] {
  const inDeg: Record<string, number> = {}
  const adj: Record<string, string[]> = {}
  flowNodes.value.forEach((n: any) => { inDeg[n.id] = 0; adj[n.id] = [] })
  flowEdges.value.forEach((e: any) => { adj[e.source]?.push(e.target); inDeg[e.target] = (inDeg[e.target] || 0) + 1 })
  const queue = Object.keys(inDeg).filter(k => inDeg[k] === 0)
  const result: string[] = []
  while (queue.length) {
    const id = queue.shift()!
    result.push(id)
    for (const child of adj[id] || []) { inDeg[child]--; if (inDeg[child] === 0) queue.push(child) }
  }
  return result
}

defineExpose({ autoLayout })
</script>

<template>
  <div class="dag-canvas" @drop="onDrop" @dragover="onDragOver">
    <VueFlow v-model:nodes="flowNodes" v-model:edges="flowEdges" @node-context-menu="(onNodeContextMenu as any)" @node-double-click="(onNodeDoubleClick as any)" fit-view-on-init>
      <template #node-component-node="nodeProps">
        <DagCustomNode :data="nodeProps.data" />
      </template>
      <Background />
      <Controls />
    </VueFlow>
    <DagContextMenu ref="contextMenu" @skip="skipNode" @unskip="unskipNode" @delete="deleteNode" @config="(id: string) => configModal?.open(id, flowNodes.find(n => n.id === id)?.data || {})" />
    <NodeConfigModal ref="configModal" @save="saveNodeConfig" @delete="deleteNode" />
  </div>
</template>

<style scoped>
.dag-canvas { flex: 1; height: 100%; }
</style>
<style>
@import '@vue-flow/core/dist/style.css';
@import '@vue-flow/core/dist/theme-default.css';
@import '@vue-flow/controls/dist/style.css';
</style>