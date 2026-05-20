import { reactive, ref, nextTick, type Ref } from 'vue'
import type { TreeNode } from './useFileTree'
import type { MenuItem } from '../components/ContextMenu.vue'
import { manualStatusOptions } from './useComponentStatus'
import type { Language, Tab } from './useTabs'

export function useContextMenu(opts: {
  folders: Ref<any[]>
  clipboard: Ref<{ kind: 'component' | 'folder'; action: 'copy' | 'cut'; id: number; type?: string; folderType?: string } | null>
  folderCollapsedGetter: (id: number) => boolean
  folderCollapsedSetter: (id: number, val: boolean) => void
  openComp: (c: any) => void
  runCode: () => void
  newBlankTab: (lang: Language, folderId?: number | null) => void
  startRename: (node: TreeNode) => void
  startRenameComponent: (node: TreeNode) => void
  startNewFolder: (type: string, parentId: number | null) => void
  confirmDeleteComp: (c: any) => Promise<void>
  deleteFolder: (id: number) => Promise<void>
  setCompStatus: (c: any, status: string) => Promise<void>
  doPaste: (targetNode: TreeNode) => Promise<void>
  doMoveComponent: (compId: number, folderId: number) => Promise<void>
  exportComponent?: (c: any) => void
}) {
  const contextMenu = reactive({
    visible: false,
    x: 0,
    y: 0,
    items: [] as MenuItem[],
  })

  const lastContextNode = ref<TreeNode | null>(null)

  function typeLabel(type: string): string {
    const map: Record<string, string> = { sql: 'SQL 查询', python: 'Python 脚本', shell: 'Shell 脚本', datax: 'DataX 同步' }
    return map[type] || type
  }

  function buildCompMenuItems(node: TreeNode): MenuItem[] {
    const c = node.data
    const t = c.type as string
    const items: MenuItem[] = []

    if (t === 'datax') {
      items.push({ key: 'open', label: '打开' })
      items.push({ divider: true })
      items.push({ key: 'delete', label: '删除', danger: true })
      return items
    }

    items.push({ key: 'open', label: '打开' })
    items.push({ key: 'run', label: '运行' })
    items.push({ divider: true })
    items.push({ key: `new-${t}`, label: `新建${typeLabel(t)}` })
    items.push({ key: 'copy', label: '复制' })
    items.push({ key: 'cut', label: '剪切' })
    if (opts.clipboard.value && opts.clipboard.value.kind === 'component') {
      items.push({ key: 'paste', label: '粘贴' })
    }
    items.push({ divider: true })
    items.push({ key: 'rename', label: '重命名' })
    items.push({
      key: 'move',
      label: '移动到其他文件夹',
      children: buildMoveToFolderMenu(t, 'move-to'),
    })
    items.push({ divider: true })
    if (c.status === 'paused') {
      items.push({ key: 'resume', label: '从暂停恢复' })
    } else if (c.status !== 'archived') {
      items.push({
        key: 'status',
        label: '设置状态',
        children: buildStatusSubmenu(c.status),
      })
    }
    items.push({ key: 'export', label: '导出' })
    items.push({ divider: true })
    items.push({ key: 'delete', label: '删除', danger: true })
    return items
  }

  function buildFolderMenuItems(node: TreeNode): MenuItem[] {
    const items: MenuItem[] = []
    const collapsed = opts.folderCollapsedGetter(node.id)
    const t = node.folderType
    items.push({ key: collapsed ? 'expand' : 'collapse', label: collapsed ? '展开' : '折叠' })
    items.push({ divider: true })
    if (node.depth < 3) {
      items.push({ key: 'new-subfolder', label: '新建子文件夹' })
    }
    items.push({ key: `new-${t}`, label: `新建${typeLabel(t)}` })
    items.push({ divider: true })
    items.push({ key: 'rename', label: '重命名' })
    items.push({ key: 'cut', label: '剪切' })
    if (opts.clipboard.value && opts.clipboard.value.kind === 'folder') {
      items.push({ key: 'paste', label: '粘贴' })
    }
    items.push({ divider: true })
    items.push({ key: 'delete', label: '删除', danger: true })
    return items
  }

  function buildStatusSubmenu(current: string): MenuItem[] {
    const statusOpts = manualStatusOptions(current)
    return statusOpts.map(o => ({
      key: `status-${o.value}`,
      label: o.label,
      icon: 'dot',
    }))
  }

  function buildMoveToFolderMenu(type: string, prefix: string): MenuItem[] {
    const typeFolders = opts.folders.value.filter(f => f.type === type)
    const roots = typeFolders.filter(f => f.parent_id == null)
    function buildSub(foldersList: any[]): MenuItem[] {
      return foldersList.map(f => {
        const children = typeFolders.filter(child => child.parent_id === f.id)
        const item: MenuItem = { key: `${prefix}-${f.id}`, label: f.name }
        if (children.length > 0) {
          item.children = buildSub(children)
        }
        return item
      })
    }
    const menu = buildSub(roots)
    menu.unshift({ key: `${prefix}-0`, label: '（无文件夹）' })
    return menu
  }

  async function onMenuSelect(key: string) {
    const targetNode = lastContextNode.value
    if (!targetNode) return

    if (key === 'open') {
      if (targetNode.kind === 'component') opts.openComp(targetNode.data)
    } else if (key === 'run') {
      if (targetNode.kind === 'component') {
        opts.openComp(targetNode.data)
        await nextTick()
        opts.runCode()
      }
    } else if (key === 'expand') {
      opts.folderCollapsedSetter(targetNode.id, false)
    } else if (key === 'collapse') {
      opts.folderCollapsedSetter(targetNode.id, true)
    } else if (key === 'copy') {
      if (targetNode.kind === 'component') {
        opts.clipboard.value = { kind: 'component', action: 'copy', id: targetNode.id, type: targetNode.data.type }
      }
    } else if (key === 'cut') {
      if (targetNode.kind === 'component') {
        opts.clipboard.value = { kind: 'component', action: 'cut', id: targetNode.id, type: targetNode.data.type }
      } else if (targetNode.kind === 'folder') {
        opts.clipboard.value = { kind: 'folder', action: 'cut', id: targetNode.id, folderType: targetNode.folderType }
      }
    } else if (key === 'paste') {
      await opts.doPaste(targetNode)
    } else if (key === 'rename') {
      if (targetNode.kind === 'folder') opts.startRename(targetNode)
      else if (targetNode.kind === 'component') opts.startRenameComponent(targetNode)
    } else if (key === 'delete') {
      if (targetNode.kind === 'component') await opts.confirmDeleteComp(targetNode.data)
      else if (targetNode.kind === 'folder') await opts.deleteFolder(targetNode.id)
    } else if (key === 'new-subfolder') {
      if (targetNode.kind === 'folder') opts.startNewFolder(targetNode.folderType, targetNode.id)
    } else if (key === 'resume') {
      if (targetNode.kind === 'component') await opts.setCompStatus(targetNode.data, '__resume__')
    } else if (key.startsWith('status-')) {
      const status = key.replace('status-', '')
      if (targetNode.kind === 'component') await opts.setCompStatus(targetNode.data, status)
    } else if (key.startsWith('move-to-')) {
      const folderId = parseInt(key.replace('move-to-', ''), 10)
      if (targetNode.kind === 'component') await opts.doMoveComponent(targetNode.data.id, folderId)
    } else if (key === 'export') {
      if (targetNode.kind === 'component' && opts.exportComponent) {
        opts.exportComponent(targetNode.data)
      }
    } else if (key.startsWith('new-')) {
      const lang = key.replace('new-', '') as Language
      const folderId = targetNode.kind === 'folder' ? targetNode.id : (targetNode.data?.folder_id ?? null)
      opts.newBlankTab(lang, folderId)
    }
  }

  function showCompContextMenu(e: MouseEvent, node: TreeNode) {
    lastContextNode.value = node
    contextMenu.x = e.clientX
    contextMenu.y = e.clientY
    contextMenu.items = buildCompMenuItems(node)
    contextMenu.visible = true
  }

  function showFolderContextMenu(e: MouseEvent, node: TreeNode) {
    lastContextNode.value = node
    contextMenu.x = e.clientX
    contextMenu.y = e.clientY
    contextMenu.items = buildFolderMenuItems(node)
    contextMenu.visible = true
  }

  return {
    contextMenu,
    lastContextNode,
    buildCompMenuItems,
    buildFolderMenuItems,
    onMenuSelect,
    showCompContextMenu,
    showFolderContextMenu,
  }
}
