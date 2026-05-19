<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getComponentFolders, getComponents, getSyncTasks } from '../../api'
import { TYPE_GROUPS_WITH_DATAX } from '../../composables/useFileTree'
import type { TreeNode } from '../../composables/useFileTree'
import FileTreePanel from '../FileTreePanel.vue'

const components = ref<any[]>([])
const folders = ref<any[]>([])

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

function onDragStart(event: DragEvent, node: TreeNode) {
  event.dataTransfer!.setData('application/dag-component', JSON.stringify(node.data))
  event.dataTransfer!.effectAllowed = 'move'
}
</script>

<template>
  <FileTreePanel
    title="任务节点"
    :groups="TYPE_GROUPS_WITH_DATAX"
    :components="components"
    :folders="folders"
    :default-collapsed="true"
    :draggable="true"
    @node-dragstart="onDragStart"
  />
</template>

<style scoped>
:deep(.ftp) { width: 260px; }
</style>
