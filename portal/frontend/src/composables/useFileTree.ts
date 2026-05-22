import { ref, computed, reactive } from 'vue'

// ── 类型定义 ─────────────────────────────────────────────────────────────

export interface TypeGroup {
  type: string
  label: string
  color: string
  gradient: string
  abbr: string
}

export interface TreeNode {
  nodeKey: string
  kind: 'folder' | 'component'
  id: number
  name: string
  depth: number
  folderType: string
  data?: any
}

// ── 所有页面共用的类型分组定义 ────────────────────────────────────────────

export const TYPE_GROUPS: TypeGroup[] = [
  { type: 'sql',       label: 'SQL 查询',    color: '#D97706', gradient: 'linear-gradient(135deg, #D97706 0%, #F59E0B 100%)', abbr: 'SQ'  },
  { type: 'python',    label: 'Python 脚本', color: '#3776AB', gradient: 'linear-gradient(135deg, #3776AB 0%, #5B9FD4 100%)', abbr: 'PY'  },
  { type: 'shell',     label: 'Shell 脚本',  color: '#4EAA25', gradient: 'linear-gradient(135deg, #4EAA25 0%, #6DC940 100%)', abbr: 'SH'  },
  { type: 'procedure', label: '存储过程',    color: '#0EA5E9', gradient: 'linear-gradient(135deg, #0EA5E9 0%, #38BDF8 100%)', abbr: 'PR'  },
]

export const TYPE_GROUPS_WITH_DATAX: TypeGroup[] = [
  ...TYPE_GROUPS,
  { type: 'datax',  label: 'DataX 同步',  color: '#7C3AED', gradient: 'linear-gradient(135deg, #7C3AED 0%, #A855F7 100%)', abbr: 'DX'  },
]

// ── flatTree composable ───────────────────────────────────────────────────

export interface UseFileTreeOptions {
  /** 初始是否折叠所有组（默认 false） */
  defaultCollapsed?: boolean
  /** 要包含的类型组（默认 TYPE_GROUPS_WITH_DATAX） */
  groups?: TypeGroup[]
}

export function useFileTree(
  components: { value: any[] },
  folders: { value: any[] },
  searchKw: { value: string },
  options?: UseFileTreeOptions,
) {
  const groups = options?.groups ?? TYPE_GROUPS_WITH_DATAX
  const grpCollapsed = reactive<Record<string, boolean>>(
    Object.fromEntries(groups.map(g => [g.type, options?.defaultCollapsed ?? false]))
  )
  const folderCollapsed = reactive<Record<number, boolean>>({})

  function toggleGrp(type: string) {
    grpCollapsed[type] = !grpCollapsed[type]
  }
  function toggleFolder(id: number) {
    folderCollapsed[id] = !folderCollapsed[id]
  }

  function compCountByType(type: string) {
    return components.value.filter(c => c.type === type).length
  }

  function flatTree(type: string): TreeNode[] {
    const kw = searchKw.value.trim().toLowerCase()
    const searching = kw.length > 0
    const typeComps = components.value.filter(c =>
      c.type === type && (!searching || c.name.toLowerCase().includes(kw))
    )
    const typeFolders = folders.value.filter(f => f.type === type)
    const validFolderIds = new Set(typeFolders.map(f => f.id))
    const result: TreeNode[] = []

    function folderHasMatch(fid: number): boolean {
      if (typeComps.some(c => c.folder_id === fid)) return true
      return typeFolders
        .filter(f => f.parent_id === fid)
        .some(child => folderHasMatch(child.id))
    }

    function traverse(parentId: number | null, depth: number) {
      const childFolders = typeFolders
        .filter(f => (f.parent_id ?? null) === parentId)
        .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id)
      for (const f of childFolders) {
        if (searching && !folderHasMatch(f.id)) continue
        result.push({ nodeKey: `f-${f.id}`, kind: 'folder', id: f.id, name: f.name, depth, folderType: type })
        if (searching || !folderCollapsed[f.id]) traverse(f.id, depth + 1)
      }
      const childComps = typeComps
        .filter(c => {
          const fid = c.folder_id ?? null
          if (parentId === null) return fid === null || !validFolderIds.has(fid)
          return fid === parentId
        })
        .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || b.id - a.id)
      for (const c of childComps) {
        result.push({ nodeKey: `c-${c.id}`, kind: 'component', id: c.id, name: c.name, depth, folderType: type, data: c })
      }
    }

    traverse(null, 0)
    return result
  }

  return { grpCollapsed, folderCollapsed, toggleGrp, toggleFolder, compCountByType, flatTree }
}
