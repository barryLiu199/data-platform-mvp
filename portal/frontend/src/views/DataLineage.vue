<template>
  <div class="page">
    <PageHeader title="数据血缘" description="自动解析组件代码，追踪数据流转关系">
      <template #actions>
        <a-button @click="loadLineage" :loading="loading">
          <template #icon><icon-refresh /></template>
          刷新
        </a-button>
      </template>
    </PageHeader>

    <div class="glass-card lineage-body" v-if="!loading && nodes.length">
      <!-- 分层展示 -->
      <div class="lineage-flow">
        <div class="lineage-layer" v-if="sourceNodes.length">
          <div class="layer-label">数据源层</div>
          <div class="layer-items">
            <div v-for="n in sourceNodes" :key="n.id" class="node source" :class="{ highlighted: highlighted.has(n.id) }" @click="highlight(n.id)">
              <div class="node-name">{{ n.name }}</div>
              <div class="node-meta">{{ n.datasource || '' }}</div>
            </div>
          </div>
        </div>

        <div class="arrow-group" v-if="sourceNodes.length && odsNodes.length">
          <div class="arrow-line"></div>
          <div class="arrow-label">DataX / SQL</div>
          <div class="arrow-line"></div>
        </div>

        <div class="lineage-layer" v-if="odsNodes.length">
          <div class="layer-label">ODS 贴源层</div>
          <div class="layer-items">
            <div v-for="n in odsNodes" :key="n.id" class="node ods" :class="{ highlighted: highlighted.has(n.id) }" @click="highlight(n.id)">
              <div class="node-badge ods-badge">ODS</div>
              <div class="node-name">{{ n.name }}</div>
            </div>
          </div>
        </div>

        <div class="arrow-group" v-if="odsNodes.length && appNodes.length">
          <div class="arrow-line"></div>
          <div class="arrow-label">ETL / SQL</div>
          <div class="arrow-line"></div>
        </div>

        <div class="lineage-layer" v-if="appNodes.length">
          <div class="layer-label">DW / ADS 应用层</div>
          <div class="layer-items">
            <div v-for="n in appNodes" :key="n.id" class="node app" :class="{ highlighted: highlighted.has(n.id) }" @click="highlight(n.id)">
              <div class="node-badge app-badge">{{ n.name.startsWith('dim') ? 'DIM' : 'ADS' }}</div>
              <div class="node-name">{{ n.name }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 边列表 -->
      <div class="edge-list" v-if="edges.length">
        <div class="edge-title">血缘关系 ({{ edges.length }})</div>
        <div class="edge-table">
          <div v-for="(e, i) in edges" :key="i" class="edge-row">
            <code class="edge-node">{{ e.source }}</code>
            <span class="edge-arrow">→</span>
            <code class="edge-node">{{ e.target }}</code>
            <a-tag size="small" :color="e.type === 'DataX' ? 'purple' : 'blue'">{{ e.type }}</a-tag>
            <span class="edge-task">{{ e.task_name }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="glass-card empty-card" v-else-if="!loading">
      <div class="empty-state">
        <p>暂无血缘数据</p>
        <p class="text-muted">发布组件或创建同步任务后，系统将自动解析数据流转关系</p>
      </div>
    </div>

    <div class="glass-card loading-card" v-else>
      <a-spin dot /><span class="text-muted" style="margin-left:8px">正在解析血缘...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { IconRefresh } from '@arco-design/web-vue/es/icon'
import PageHeader from '../components/PageHeader.vue'
import { getMetadataLineage } from '../api'

interface Node { id: string; name: string; datasource?: string; layer: string }
interface Edge { source: string; target: string; type: string; task_name?: string }

const loading = ref(false)
const nodes = ref<Node[]>([])
const edges = ref<Edge[]>([])
const highlighted = ref<Set<string>>(new Set())

const sourceNodes = computed(() => nodes.value.filter(n => n.layer === 'source'))
const odsNodes = computed(() => nodes.value.filter(n => n.layer === 'ods'))
const appNodes = computed(() => nodes.value.filter(n => n.layer === 'app'))

function highlight(nodeId: string) {
  const s = new Set<string>()
  s.add(nodeId)
  // 找上下游
  for (const e of edges.value) {
    if (e.source === nodeId) s.add(e.target)
    if (e.target === nodeId) s.add(e.source)
  }
  highlighted.value = s
}

async function loadLineage() {
  loading.value = true
  highlighted.value = new Set()
  try {
    const res: any = await getMetadataLineage()
    nodes.value = res?.nodes || []
    edges.value = res?.edges || []
  } catch { nodes.value = []; edges.value = [] }
  loading.value = false
}

onMounted(() => { loadLineage() })
</script>

<style scoped>
.page { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.lineage-body { padding: var(--space-6); }
.lineage-flow { display: flex; flex-direction: column; align-items: center; gap: 0; }
.lineage-layer { width: 100%; text-align: center; }
.layer-label { font-size: 11px; color: var(--color-text-tertiary); margin-bottom: 10px; text-transform: uppercase; letter-spacing: 2px; font-weight: var(--font-weight-semibold); }
.layer-items { display: flex; gap: var(--space-3); justify-content: center; flex-wrap: wrap; }

.node {
  background: var(--color-bg-surface); border: 1.5px solid var(--color-border); border-radius: var(--radius-lg);
  padding: var(--space-3) 18px; min-width: 120px; text-align: center; cursor: pointer; transition: all 0.2s;
}
.node:hover { border-color: var(--color-primary-border); box-shadow: 0 2px 8px rgba(37,99,235,0.08); }
.node.highlighted { border-color: var(--color-primary); box-shadow: 0 0 0 2px rgba(37,99,235,0.15); }
.node-badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 10px; font-weight: var(--font-weight-semibold); margin-bottom: 6px; }
.ods-badge { background: var(--color-success-light); color: var(--color-success); }
.app-badge { background: var(--color-warning-light); color: var(--color-warning); }
.node-name { font-size: var(--font-size-xs); font-weight: var(--font-weight-semibold); color: var(--color-text-primary); font-family: var(--font-family-mono); }
.node-meta { font-size: 10px; color: var(--color-text-tertiary); margin-top: 2px; }

.arrow-group { display: flex; flex-direction: column; align-items: center; padding: var(--space-2) 0; }
.arrow-line { width: 1.5px; height: 16px; background: linear-gradient(to bottom, var(--color-border), var(--color-primary)); }
.arrow-label { font-size: 10px; color: var(--color-primary); background: var(--color-primary-light); padding: 2px 10px; border-radius: 10px; margin: var(--space-1) 0; font-weight: 500; }

.edge-list { margin-top: 28px; border-top: 1px solid var(--color-border-subtle); padding-top: var(--space-4); }
.edge-title { font-size: var(--font-size-sm); font-weight: var(--font-weight-semibold); color: var(--color-text-primary); margin-bottom: 10px; }
.edge-table { display: flex; flex-direction: column; gap: 6px; }
.edge-row { display: flex; align-items: center; gap: var(--space-2); padding: 6px 10px; background: var(--color-bg-elevated); border-radius: var(--radius-sm); font-size: var(--font-size-xs); }
.edge-node { font-family: var(--font-family-mono); color: var(--color-text-primary); }
.edge-arrow { color: var(--color-text-tertiary); }
.edge-task { color: var(--color-text-tertiary); font-size: 11px; margin-left: auto; }

.empty-card, .loading-card { padding: 60px 0; text-align: center; }
.text-muted { color: var(--color-text-tertiary); }
.empty-state { padding: var(--space-10) 0; text-align: center; }
</style>
