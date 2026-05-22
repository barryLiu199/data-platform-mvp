import { ref, computed, type Ref } from 'vue'

export type Language = 'sql' | 'python' | 'shell' | 'datax' | 'procedure'

export interface Tab {
  key: string
  name: string
  code: string
  language: Language
  componentId?: number
  folderId?: number | null
  datasourceId?: number
  syncTaskId?: number | null
  localParams?: { prop: string; direct: string; type: string; value: string }[]
  /** procedure 类型专用配置 */
  procedure?: {
    procedure_name: string
    params: string[]
    timeout: number
  }
  dirty: boolean
}

export function useTabs(
  components: Ref<any[]>,
  datasources: Ref<any[]>,
  loadComponents: () => Promise<void>,
) {
  const tabs = ref<Tab[]>([])
  const activeKey = ref('')
  const activeTab = computed<Tab | null>(() => tabs.value.find(t => t.key === activeKey.value) ?? null)
  const editorRef = ref<any>(null)

  let tabSeq = 0
  function genKey() { return `tab-${++tabSeq}` }

  function isTabActive(compId: number) {
    return activeTab.value?.componentId === compId
  }

  function openComp(c: any) {
    if (c.type === 'datax') {
      const existing = tabs.value.find(t => t.componentId === c.id)
      if (existing) { switchTab(existing.key); return }
      const key = genKey()
      const cfg = c.config_json || {}
      tabs.value.push({
        key,
        name: c.name,
        code: '',
        language: 'datax',
        componentId: c.id,
        folderId: c.folder_id ?? null,
        syncTaskId: cfg.sync_task_id ?? null,
        dirty: false,
      })
      switchTab(key)
      return
    }
    if (c.type === 'procedure') {
      const existing = tabs.value.find(t => t.componentId === c.id)
      if (existing) { switchTab(existing.key); return }
      const key = genKey()
      const cfg = c.config_json || {}
      tabs.value.push({
        key,
        name: c.name,
        code: '',
        language: 'procedure',
        componentId: c.id,
        folderId: c.folder_id ?? null,
        datasourceId: cfg.datasource_id,
        procedure: {
          procedure_name: cfg.procedure_name || '',
          params: Array.isArray(cfg.params) ? [...cfg.params] : [],
          timeout: typeof cfg.timeout === 'number' ? cfg.timeout : 3600,
        },
        dirty: false,
      })
      switchTab(key)
      return
    }
    const existing = tabs.value.find(t => t.componentId === c.id)
    if (existing) { switchTab(existing.key); return }
    const key = genKey()
    const cfg = c.config_json || {}
    const code = cfg.sql || cfg.script || c.code || ''
    tabs.value.push({
      key,
      name: c.name,
      code,
      language: c.type as Language,
      componentId: c.id,
      folderId: c.folder_id ?? null,
      localParams: cfg.localParams || [],
      datasourceId: (() => {
        const rawId = cfg.datasource_id || c.datasource_id || undefined
        if (rawId == null) return undefined
        const validIds = new Set(datasources.value.map((d: any) => d.id))
        return validIds.has(rawId) ? rawId : undefined
      })(),
      dirty: false,
    })
    switchTab(key)
  }

  function newBlankTab(lang: Language = 'sql', folderId?: number | null) {
    if (lang === 'datax') {
      const key = genKey()
      tabs.value.push({ key, name: '新建同步任务', code: '', language: 'datax', folderId: folderId ?? null, syncTaskId: null, dirty: false })
      switchTab(key)
      return
    }
    if (lang === 'procedure') {
      const key = genKey()
      tabs.value.push({
        key,
        name: 'Untitled 存储过程',
        code: '',
        language: 'procedure',
        folderId: folderId ?? null,
        procedure: { procedure_name: '', params: [], timeout: 3600 },
        dirty: false,
      })
      switchTab(key)
      return
    }
    const key = genKey()
    const names: Record<string, string> = { sql: 'Untitled SQL', python: 'Untitled Python', shell: 'Untitled Shell', procedure: 'Untitled 存储过程' }
    tabs.value.push({ key, name: names[lang] ?? 'Untitled', code: '', language: lang, folderId: folderId ?? null, dirty: false })
    switchTab(key)
  }

  function switchTab(key: string) { activeKey.value = key }

  function closeTab(key: string) {
    const idx = tabs.value.findIndex(t => t.key === key)
    if (idx === -1) return
    tabs.value.splice(idx, 1)
    if (activeKey.value === key) activeKey.value = tabs.value[Math.max(0, idx - 1)]?.key ?? ''
  }

  function onCodeChange(v: string) {
    const tab = activeTab.value
    if (tab) { tab.code = v; tab.dirty = true }
  }

  function formatSQL() {
    editorRef.value?.formatDocument?.()
    const tab = activeTab.value
    if (tab) tab.dirty = true
  }

  function onDataxSaved(res: any) {
    const tab = activeTab.value
    if (res._component && tab) {
      tab.syncTaskId = res.id
      tab.componentId = res._component.id
      const src = res.source_table || ''
      const dst = res.target_table || ''
      tab.name = src && dst ? `${src} → ${dst}` : (res.name || tab.name)
      tab.dirty = false
    }
    loadComponents()
  }

  return {
    tabs,
    activeKey,
    activeTab,
    editorRef,
    genKey,
    isTabActive,
    openComp,
    newBlankTab,
    switchTab,
    closeTab,
    onCodeChange,
    formatSQL,
    onDataxSaved,
  }
}
