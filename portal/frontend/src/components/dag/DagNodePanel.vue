<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { getComponentFolders, getComponents, getSyncTasks } from '../../api'
import { useFileTree, TYPE_GROUPS_WITH_DATAX } from '../../composables/useFileTree'
import { IconSearch } from '@arco-design/web-vue/es/icon'
import LangIcon from '../LangIcon.vue'

const components = ref<any[]>([])
const folders = ref<any[]>([])
const searchKw = ref('')

const { grpCollapsed, folderCollapsed, toggleGrp, toggleFolder, compCountByType, flatTree } =
  useFileTree(components, folders, searchKw)

Object.assign(grpCollapsed, { sql: true, python: true, shell: true, datax: true })

onMounted(async () => {
  const [fRes, cRes, sRes]: any[] = await Promise.all([
    getComponentFolders(),
    getComponents({ status: 'online', page_size: 500 }),
    getSyncTasks({ status: 'active', page_size: 500 }),
  ])
  folders.value = Array.isArray(fRes) ? fRes : (fRes.items || [])
  const comps = cRes.items || []
  const syncTasks = (sRes.items || []).map((t: any) => ({
    id: t.id,
    name: t.name,
    type: 'datax',
    status: 'online',
    folder_id: null,
    _isSyncTask: true,
    _syncTaskId: t.id,
  }))
  components.value = [...comps, ...syncTasks]
})

function onDragStart(event: DragEvent, comp: any) {
  event.dataTransfer!.setData('application/dag-component', JSON.stringify(comp))
  event.dataTransfer!.effectAllowed = 'move'
}
</script>

<template>
  <div class="dag-panel">
    <div class="dag-panel__header">
      <span class="dag-panel__title">组件库</span>
    </div>
    <div class="dag-panel__search">
      <a-input v-model="searchKw" placeholder="搜索组件..." size="small" allow-clear>
        <template #prefix><icon-search /></template>
      </a-input>
    </div>

    <div class="dag-panel__tree">
      <template v-for="grp in TYPE_GROUPS_WITH_DATAX" :key="grp.type">
        <div class="grp-header" @click="toggleGrp(grp.type)">
          <span class="grp-caret" :class="{ collapsed: grpCollapsed[grp.type] }">▾</span>
          <LangIcon :type="grp.type" :size="18" class="grp-lang-icon" />
          <span class="grp-label">{{ grp.label }}</span>
          <span class="grp-count">{{ compCountByType(grp.type) }}</span>
        </div>

        <template v-if="searchKw || !grpCollapsed[grp.type]">
          <template v-for="node in flatTree(grp.type)" :key="node.nodeKey">

            <!-- 文件夹 -->
            <div v-if="node.kind === 'folder'"
              class="tree-node folder-node"
              :style="{ paddingLeft: `${14 + node.depth * 14}px` }"
              @click="toggleFolder(node.id)">
              <span class="node-caret">{{ folderCollapsed[node.id] ? '▸' : '▾' }}</span>
              <span class="folder-icon">📁</span>
              <span class="node-name">{{ node.name }}</span>
            </div>

            <!-- 组件 -->
            <div v-else
              class="tree-node comp-node"
              :style="{ paddingLeft: `${14 + node.depth * 14}px` }"
              draggable="true"
              @dragstart="onDragStart($event, node.data)">
              <LangIcon :type="node.data.type" :size="18" />
              <span class="node-name">{{ node.name }}</span>
              <span class="drag-hint">⠿</span>
            </div>

          </template>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
.dag-panel { width: 260px; border-right: 1px solid #e5e7eb; display: flex; flex-direction: column; background: #fafbfc; overflow: hidden; }
.dag-panel__header { padding: 10px 14px 8px; border-bottom: 1px solid #e5e7eb; }
.dag-panel__title { font-size: 13px; font-weight: 600; color: #1d2129; }
.dag-panel__search { padding: 6px 10px; border-bottom: 1px solid #f2f3f5; }
.dag-panel__tree { flex: 1; overflow-y: auto; padding: 4px 0; }

.grp-header { display: flex; align-items: center; gap: 6px; padding: 5px 10px; cursor: pointer; font-size: 11px; font-weight: 600; color: #4e5969; user-select: none; transition: background 0.15s; }
.grp-header:hover { background: #f2f3f5; }
.grp-caret { font-size: 12px; color: #86909c; transition: transform 0.2s; display: inline-block; }
.grp-caret.collapsed { transform: rotate(-90deg); }
.grp-lang-icon { border-radius: 4px; }
.grp-label { flex: 1; }
.grp-count { font-size: 10px; background: #e5e6eb; color: #86909c; padding: 0 5px; border-radius: 8px; min-width: 16px; text-align: center; }

.tree-node { display: flex; align-items: center; gap: 6px; height: 28px; font-size: 12px; cursor: pointer; transition: background 0.12s; padding-right: 8px; }
.tree-node:hover { background: #f2f3f5; }

.folder-node { color: #4e5969; font-weight: 500; }
.node-caret { font-size: 10px; color: #86909c; flex-shrink: 0; }
.folder-icon { font-size: 13px; color: #F7BA1E; flex-shrink: 0; }

.comp-node { color: #1d2129; cursor: grab; }
.comp-node:hover { background: #eaf1ff; }
.comp-node:active { cursor: grabbing; }
.comp-node:hover .drag-hint { opacity: 1; }

.node-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.drag-hint { font-size: 12px; color: #c9cdd4; opacity: 0; transition: opacity 0.15s; flex-shrink: 0; }
</style>
