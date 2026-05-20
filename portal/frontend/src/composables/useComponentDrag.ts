import { reactive, type Ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { moveComponent, reorderComponents, moveComponentFolder } from '../api'
import type { TreeNode } from './useFileTree'

export function useComponentDrag(
  components: Ref<any[]>,
  folders: Ref<any[]>,
  loadComponents: () => Promise<void>,
  loadFolders: () => Promise<void>,
) {
  // ---- 拖拽状态 ----
  const dragState = reactive({
    draggingId: null as number | null,
    dragKind: null as 'component' | 'folder' | null,
    dragFolderType: null as string | null,
    dragFolderId: null as number | null,
    dropTargetId: null as number | string | null,
    dropKind: null as 'component' | 'folder' | 'group' | null,
    dropPosition: null as 'before' | 'after' | 'inside' | null,
  })

  // ---- CSS class 映射 ----
  function getNodeClass(node: TreeNode) {
    return {
      'dragging': dragState.draggingId === node.id && dragState.dragKind === 'component',
      'drop-target': dragState.dropTargetId === node.id && dragState.dropKind === 'component',
      'drop-before': dragState.dropTargetId === node.id && dragState.dropPosition === 'before',
      'drop-after': dragState.dropTargetId === node.id && dragState.dropPosition === 'after',
    }
  }

  function getFolderClass(node: TreeNode) {
    return {
      'dragging': dragState.draggingId === node.id && dragState.dragKind === 'folder',
      'drop-target': dragState.dropTargetId === node.id && dragState.dropKind === 'folder',
    }
  }

  function getGroupClass(group: { type: string }) {
    return {
      'drop-target': dragState.dropTargetId === group.type && dragState.dropKind === 'group',
    }
  }

  // ---- 拖拽事件处理 ----
  function onCompDragStart(e: DragEvent, node: TreeNode) {
    dragState.draggingId = node.id
    dragState.dragKind = node.kind
    dragState.dragFolderType = node.folderType
    dragState.dragFolderId = node.data?.folder_id ?? null
    e.dataTransfer!.effectAllowed = 'move'
    e.dataTransfer!.setData('application/json', JSON.stringify({
      id: node.id,
      kind: node.kind,
      folderType: node.folderType,
      type: node.data?.type,
      folderId: node.data?.folder_id,
    }))
  }

  /** 检查拖拽文件夹是否包含目标文件夹（防止循环引用） */
  function folderContains(parentId: number, childId: number): boolean {
    const children = folders.value.filter(f => f.parent_id === parentId)
    for (const child of children) {
      if (child.id === childId) return true
      if (folderContains(child.id, childId)) return true
    }
    return false
  }

  function onDragOverNode(e: DragEvent, targetNode: TreeNode) {
    e.preventDefault()
    if (dragState.draggingId === targetNode.id) {
      dragState.dropTargetId = null
      dragState.dropKind = null
      dragState.dropPosition = null
      e.dataTransfer!.dropEffect = 'none'
      return
    }
    if (dragState.dragFolderType !== targetNode.folderType) {
      dragState.dropTargetId = null
      dragState.dropKind = null
      dragState.dropPosition = null
      e.dataTransfer!.dropEffect = 'none'
      return
    }
    if (dragState.dragKind === 'folder' && targetNode.kind === 'component') {
      dragState.dropTargetId = null
      dragState.dropKind = null
      dragState.dropPosition = null
      e.dataTransfer!.dropEffect = 'none'
      return
    }
    if (dragState.dragKind === 'folder' && targetNode.kind === 'folder') {
      if (dragState.draggingId! === targetNode.id || folderContains(dragState.draggingId!, targetNode.id)) {
        dragState.dropTargetId = null
        dragState.dropKind = null
        dragState.dropPosition = null
        e.dataTransfer!.dropEffect = 'none'
        return
      }
    }
    e.dataTransfer!.dropEffect = 'move'
    dragState.dropTargetId = targetNode.id
    dragState.dropKind = targetNode.kind
    if (targetNode.kind === 'folder') {
      dragState.dropPosition = 'inside'
    } else {
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
      const midY = rect.top + rect.height / 2
      dragState.dropPosition = e.clientY < midY ? 'before' : 'after'
    }
  }

  async function onDropOnNode(e: DragEvent, targetNode: TreeNode) {
    e.preventDefault()
    const dataStr = e.dataTransfer!.getData('application/json')
    if (!dataStr) return
    const data = JSON.parse(dataStr)
    if (dragState.dragFolderType !== targetNode.folderType) return

    if (data.kind === 'component' && targetNode.kind === 'folder') {
      await doMoveComponent(data.id, targetNode.id)
    } else if (data.kind === 'component' && targetNode.kind === 'component') {
      if (data.folderId === targetNode.data?.folder_id) {
        await doReorderBetween(data.id, targetNode.id, (dragState.dropPosition === 'inside' ? 'before' : dragState.dropPosition) ?? 'before')
      } else {
        await doMoveComponent(data.id, targetNode.data?.folder_id ?? 0)
        await loadComponents()
        await doReorderBetween(data.id, targetNode.id, (dragState.dropPosition === 'inside' ? 'before' : dragState.dropPosition) ?? 'before')
      }
    } else if (dragState.dragKind === 'folder' && targetNode.kind === 'folder') {
      if (dragState.draggingId! === targetNode.id || folderContains(dragState.draggingId!, targetNode.id)) return
      await doMoveFolder(data.id, targetNode.id)
    }

    resetDragState()
  }

  function onDragEnd(_e?: DragEvent, _node?: TreeNode) {
    resetDragState()
  }

  /** 拖拽经过类型组标题 */
  function onDragOverGroup(e: DragEvent, group: { type: string }) {
    const groupType = group.type
    e.preventDefault()
    if (dragState.dragFolderType !== groupType) {
      e.dataTransfer!.dropEffect = 'none'
      dragState.dropTargetId = null
      dragState.dropKind = null
      dragState.dropPosition = null
      return
    }
    if (dragState.dragKind === 'folder') {
      e.dataTransfer!.dropEffect = 'none'
      dragState.dropTargetId = null
      dragState.dropKind = null
      dragState.dropPosition = null
      return
    }
    e.dataTransfer!.dropEffect = 'move'
    dragState.dropTargetId = groupType
    dragState.dropKind = 'group'
    dragState.dropPosition = null
  }

  /** 组件拖到类型组标题 = 移到根目录 */
  async function onDropGroup(e: DragEvent, group: { type: string }) {
    const groupType = group.type
    e.preventDefault()
    const dataStr = e.dataTransfer!.getData('application/json')
    if (!dataStr) return
    const data = JSON.parse(dataStr)
    if (dragState.dragFolderType !== groupType) return
    if (data.kind === 'component') {
      await doMoveComponent(data.id, 0)
    }
    resetDragState()
  }

  // ---- 移动/排序操作 ----
  async function doMoveComponent(compId: number, folderId: number) {
    try {
      await moveComponent(compId, folderId)
      Message.success('移动成功')
      await loadComponents()
    } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
  }

  async function doReorderBetween(dragId: number, targetId: number, dropPosition: 'before' | 'after' = 'before') {
    const dragComp = components.value.find(c => c.id === dragId)
    const targetComp = components.value.find(c => c.id === targetId)
    if (!dragComp || !targetComp) return
    const sameFolder = components.value
      .filter(c => c.folder_id === targetComp.folder_id && c.type === targetComp.type)
      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || b.id - a.id)

    const dragIdx = sameFolder.findIndex(c => c.id === dragId)
    const targetIdx = sameFolder.findIndex(c => c.id === targetId)
    if (dragIdx === -1 || targetIdx === -1) return

    const item = sameFolder.splice(dragIdx, 1)[0]
    const insertIdx = dropPosition === 'after'
      ? (dragIdx < targetIdx ? targetIdx : targetIdx + 1)
      : (dragIdx > targetIdx ? targetIdx : targetIdx)
    sameFolder.splice(insertIdx, 0, item)

    const orders = sameFolder.map((c, i) => ({ id: c.id, sort_order: i * 10 }))
    try {
      await reorderComponents(orders)
      await loadComponents()
    } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
  }

  async function doMoveFolder(folderId: number, parentId: number) {
    try {
      await moveComponentFolder(folderId, parentId)
      Message.success('移动成功')
      await loadFolders()
    } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
  }

  function resetDragState() {
    dragState.draggingId = null
    dragState.dragKind = null
    dragState.dragFolderType = null
    dragState.dragFolderId = null
    dragState.dropTargetId = null
    dragState.dropKind = null
    dragState.dropPosition = null
  }

  return {
    dragState,
    getNodeClass,
    getFolderClass,
    getGroupClass,
    onCompDragStart,
    onDragOverNode,
    onDropOnNode,
    onDragEnd,
    onDragOverGroup,
    onDropGroup,
    folderContains,
    doMoveComponent,
    doReorderBetween,
    doMoveFolder,
  }
}
