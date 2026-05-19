<script setup lang="ts">
import { ref, toRef } from 'vue'
import { useFileTree, type TypeGroup, type TreeNode } from '../composables/useFileTree'
import { IconSearch } from '@arco-design/web-vue/es/icon'
import LangIcon from './LangIcon.vue'

const props = withDefaults(defineProps<{
  title: string
  groups: TypeGroup[]
  components: any[]
  folders: any[]
  defaultCollapsed?: boolean
  depthIndent?: number
  draggable?: boolean
  activeId?: number | null
  nodeClass?: (node: TreeNode) => any
  folderClass?: (node: TreeNode) => any
  groupClass?: (group: TypeGroup) => any
  nodeDraggable?: (node: TreeNode) => boolean
  folderDraggable?: (node: TreeNode) => boolean
}>(), {
  defaultCollapsed: false,
  depthIndent: 16,
  draggable: false,
  activeId: null,
})

const emit = defineEmits<{
  'node-click': [node: TreeNode]
  'node-contextmenu': [event: MouseEvent, node: TreeNode]
  'node-dragstart': [event: DragEvent, node: TreeNode]
  'node-dragend': [event: DragEvent, node: TreeNode]
  'node-dragover': [event: DragEvent, node: TreeNode]
  'node-drop': [event: DragEvent, node: TreeNode]
  'folder-contextmenu': [event: MouseEvent, node: TreeNode]
  'folder-dragstart': [event: DragEvent, node: TreeNode]
  'folder-dragend': [event: DragEvent, node: TreeNode]
  'folder-dragover': [event: DragEvent, node: TreeNode]
  'folder-drop': [event: DragEvent, node: TreeNode]
  'group-dragover': [event: DragEvent, group: TypeGroup]
  'group-drop': [event: DragEvent, group: TypeGroup]
}>()

const searchKw = ref('')

const { grpCollapsed, folderCollapsed, toggleGrp, toggleFolder, compCountByType, flatTree } =
  useFileTree(
    toRef(props, 'components'),
    toRef(props, 'folders'),
    searchKw,
    { defaultCollapsed: props.defaultCollapsed, groups: props.groups },
  )

function isNodeDraggable(node: TreeNode): boolean {
  if (props.nodeDraggable) return props.nodeDraggable(node)
  return props.draggable
}

function isFolderDraggable(node: TreeNode): boolean {
  if (props.folderDraggable) return props.folderDraggable(node)
  return false
}

function onCompDragStart(event: DragEvent, node: TreeNode) {
  emit('node-dragstart', event, node)
}

defineExpose({ grpCollapsed, folderCollapsed, toggleGrp, toggleFolder, compCountByType, flatTree, searchKw })
</script>

<template>
  <div class="ftp">
    <div class="ftp-header">
      <span class="ftp-title">{{ title }}</span>
    </div>
    <div class="ftp-search">
      <a-input v-model="searchKw" size="small" placeholder="搜索" allow-clear>
        <template #prefix><icon-search /></template>
      </a-input>
    </div>

    <div class="ftp-tree">
      <template v-for="grp in groups" :key="grp.type">
        <!-- 组头：彩色竖条 + 文字 -->
        <div
          class="ftp-grp"
          :class="groupClass?.(grp)"
          @click="toggleGrp(grp.type)"
          @dragover.prevent="emit('group-dragover', $event, grp)"
          @drop.prevent="emit('group-drop', $event, grp)"
        >
          <span class="ftp-grp-bar" :style="{ background: grp.color }" />
          <span class="ftp-caret" :class="{ collapsed: grpCollapsed[grp.type] }">▾</span>
          <span class="ftp-grp-label">{{ grp.label }}</span>
          <span class="ftp-grp-count">{{ compCountByType(grp.type) }}</span>
          <slot name="group-actions" :group="grp" />
        </div>

        <!-- 树节点 -->
        <template v-if="searchKw || !grpCollapsed[grp.type]">
          <template v-for="node in flatTree(grp.type)" :key="node.nodeKey">

            <!-- 文件夹 -->
            <div
              v-if="node.kind === 'folder'"
              class="ftp-node ftp-folder"
              :class="folderClass?.(node)"
              :style="{ paddingLeft: `${14 + node.depth * depthIndent}px` }"
              :draggable="isFolderDraggable(node)"
              @click="toggleFolder(node.id)"
              @contextmenu.prevent="emit('folder-contextmenu', $event, node)"
              @dragstart="emit('folder-dragstart', $event, node)"
              @dragend="emit('folder-dragend', $event, node)"
              @dragover.prevent="emit('folder-dragover', $event, node)"
              @drop.prevent="emit('folder-drop', $event, node)"
            >
              <span class="ftp-toggle" @click.stop="toggleFolder(node.id)">
                <span class="ftp-caret" :class="{ collapsed: folderCollapsed[node.id] }">▾</span>
              </span>
              <span class="ftp-folder-icon">📁</span>
              <slot name="folder-name" :node="node">
                <span class="ftp-name">{{ node.name }}</span>
              </slot>
              <slot name="folder-actions" :node="node" />
            </div>

            <!-- 组件 / 任务节点 -->
            <div
              v-else
              class="ftp-node ftp-comp"
              :class="[
                nodeClass?.(node),
                { 'ftp-active': activeId != null && node.id === activeId },
                { 'ftp-draggable': isNodeDraggable(node) },
              ]"
              :style="{ paddingLeft: `${14 + node.depth * depthIndent}px` }"
              :draggable="isNodeDraggable(node)"
              @click="emit('node-click', node)"
              @contextmenu.prevent="emit('node-contextmenu', $event, node)"
              @dragstart="onCompDragStart($event, node)"
              @dragend="emit('node-dragend', $event, node)"
              @dragover.prevent="emit('node-dragover', $event, node)"
              @drop.prevent="emit('node-drop', $event, node)"
            >
              <LangIcon :type="node.data?.type || node.folderType" :size="18" />
              <slot name="comp-name" :node="node">
                <span class="ftp-name">
                  <template v-if="node.data?.type === 'datax' && node.data?.config_json?.source_table">
                    {{ node.data.config_json.source_table }} → {{ node.data.config_json.target_table }}
                  </template>
                  <template v-else>{{ node.name }}</template>
                </span>
              </slot>
              <slot name="comp-suffix" :node="node">
                <span v-if="draggable" class="ftp-drag-hint">⠿</span>
              </slot>
            </div>

          </template>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* ---- 面板布局 ---- */
.ftp {
  display: flex;
  flex-direction: column;
  background: var(--color-bg-base);
  border-right: 1px solid var(--color-border);
  overflow: hidden;
  height: 100%;
}

.ftp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border);
}

.ftp-title {
  font-size: 14px;
  font-weight: var(--font-weight-semibold, 600);
  color: var(--color-text-primary);
}

.ftp-search {
  padding: 6px 10px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.ftp-tree {
  flex: 1;
  overflow-y: auto;
  padding: 6px 0;
}
.ftp-tree::-webkit-scrollbar { width: 6px; }
.ftp-tree::-webkit-scrollbar-thumb { background: var(--color-border-strong); border-radius: 3px; }
.ftp-tree::-webkit-scrollbar-thumb:hover { background: var(--color-text-tertiary); }

/* ---- 组头：彩色竖条设计 ---- */
.ftp-grp {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
  cursor: pointer;
  user-select: none;
  border-radius: 4px;
  margin: 1px 4px;
  transition: background 0.15s;
}
.ftp-grp:hover { background: var(--color-bg-elevated); }

.ftp-grp-bar {
  width: 4px;
  height: 16px;
  border-radius: 2px;
  flex-shrink: 0;
}

.ftp-caret {
  font-size: 11px;
  color: var(--color-text-tertiary);
  flex-shrink: 0;
  display: inline-block;
  transition: transform 0.2s;
}
.ftp-caret.collapsed { transform: rotate(-90deg); }

.ftp-grp-label { flex: 1; }

.ftp-grp-count {
  font-size: 10px;
  background: var(--color-bg-elevated);
  color: var(--color-text-tertiary);
  padding: 0 6px;
  height: 16px;
  line-height: 16px;
  border-radius: 8px;
  min-width: 16px;
  text-align: center;
  flex-shrink: 0;
}

/* 组头操作按钮（通过 slot 传入） */
.ftp-grp :deep(.grp-action) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  color: var(--color-text-tertiary);
  font-size: 14px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}
.ftp-grp:hover :deep(.grp-action) { opacity: 1; }
.ftp-grp :deep(.grp-action:hover) {
  background: var(--color-bg-surface);
  color: var(--color-primary);
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

/* ---- 树节点通用 ---- */
.ftp-node {
  display: flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.15s, color 0.15s;
  position: relative;
  padding-right: 6px;
}
.ftp-node:hover { background: var(--color-bg-elevated); }

/* ---- 文件夹 ---- */
.ftp-folder {
  color: var(--color-text-secondary);
  font-weight: 500;
}
.ftp-folder:hover :deep(.node-actions) { opacity: 1; }

.ftp-toggle {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  cursor: pointer;
}
.ftp-toggle:hover .ftp-caret { color: var(--color-primary); }

.ftp-folder-icon {
  font-size: 13px;
  color: #F7BA1E;
  flex-shrink: 0;
}

/* ---- 组件节点 ---- */
.ftp-comp {
  color: var(--color-text-primary);
}
.ftp-comp:hover { background: var(--color-primary-light); }
.ftp-comp:hover .ftp-drag-hint { opacity: 1; }

.ftp-comp.ftp-active {
  background: linear-gradient(90deg, var(--color-primary-light) 0%, rgba(37,99,235,0.06) 100%);
  color: var(--color-primary);
  font-weight: 500;
  box-shadow: inset 3px 0 0 0 var(--color-primary);
}

.ftp-comp.ftp-draggable { cursor: grab; }
.ftp-comp.ftp-draggable:active { cursor: grabbing; }

.ftp-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ftp-drag-hint {
  font-size: 12px;
  color: var(--color-text-disabled);
  opacity: 0;
  transition: opacity 0.15s;
  flex-shrink: 0;
}

/* ---- 节点操作按钮（通过 slot 传入） ---- */
.ftp-node :deep(.node-actions) {
  display: flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s;
  flex-shrink: 0;
  padding-right: 4px;
}
.ftp-node :deep(.node-action) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  color: var(--color-text-tertiary);
  font-size: 13px;
  transition: background 0.15s, color 0.15s;
}
.ftp-node :deep(.node-action:hover) {
  background: var(--color-bg-surface);
  color: var(--color-primary);
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.ftp-node :deep(.node-action.danger:hover) {
  background: var(--color-danger-light);
  color: var(--color-danger);
}

/* ---- 重命名输入框 ---- */
.ftp-node :deep(.rename-input) { flex: 1; height: 20px; font-size: 12px; }

/* ---- 状态圆点 ---- */
.ftp-node :deep(.status-dot-only) {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-right: 4px;
  opacity: 0.7;
  transition: opacity 0.15s;
}
.ftp-comp:hover :deep(.status-dot-only) { opacity: 1; }

/* ---- 拖拽状态（通过 nodeClass/folderClass 附加） ---- */
.ftp-node :deep(.dragging) { opacity: 0.6; }
.ftp-node.dragging { opacity: 0.6; background: var(--color-primary-light) !important; }
.ftp-node.drop-target { background: var(--color-primary-light) !important; border-radius: 4px; }
.ftp-folder.drop-target { box-shadow: inset 0 0 0 1px var(--color-primary); }
.ftp-comp.drop-target { background: transparent !important; }
.ftp-comp.drop-before { box-shadow: inset 0 2px 0 0 var(--color-primary); }
.ftp-comp.drop-after { box-shadow: inset 0 -2px 0 0 var(--color-primary); }
.ftp-grp.drop-target { background: var(--color-primary-light) !important; border-radius: 4px; }
</style>
