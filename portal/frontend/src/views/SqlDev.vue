<template>
  <div class="ide-wrap">
    <!-- 左侧文件夹树 -->
    <FileTreePanel
      ref="treeRef"
      title="组件开发"
      :groups="TYPE_GROUPS_WITH_DATAX"
      :components="components"
      :folders="folders"
      :active-id="activeTab?.componentId ?? null"
      :node-class="getNodeClass"
      :folder-class="getFolderClass"
      :group-class="getGroupClass"
      :node-draggable="(n) => renamingCompId !== n.id"
      :folder-draggable="(n) => renamingFolderId !== n.id"
      class="ide-sidebar"
      @node-click="(n) => openComp(n.data)"
      @node-contextmenu="showCompContextMenu"
      @node-dragstart="onDragStart"
      @node-dragend="onDragEnd"
      @node-dragover="onDragOver"
      @node-drop="onDrop"
      @folder-contextmenu="showFolderContextMenu"
      @folder-dragstart="onDragStart"
      @folder-dragend="onDragEnd"
      @folder-dragover="onDragOver"
      @folder-drop="onDrop"
      @group-dragover="onDragOverGroup"
      @group-drop="onDropGroup"
    >
      <!-- 组头操作按钮 -->
      <template #group-actions="{ group }">
        <a-tooltip v-if="userStore.hasPermission('component:write')" content="新建文件夹">
          <span class="grp-action" @click.stop="startNewFolder(group.type, null)">⊞</span>
        </a-tooltip>
        <a-tooltip v-if="userStore.hasPermission('component:write')" content="新建组件">
          <span class="grp-action" @click.stop="newBlankTab(group.type as Language)">＋</span>
        </a-tooltip>
      </template>

      <!-- 文件夹名称（支持重命名） -->
      <template #folder-name="{ node }">
        <span v-if="renamingFolderId !== node.id" class="ftp-name" @dblclick="startRename(node)">
          {{ node.name }}
        </span>
        <a-input
          v-else
          v-model="renameValue"
          size="mini"
          class="rename-input"
          @blur="submitRename(node.id)"
          @keyup.enter="submitRename(node.id)"
          @keyup.escape="renamingFolderId = null"
          @dragstart.stop.prevent
          ref="renameInputRef"
        />
      </template>

      <!-- 文件夹操作按钮 -->
      <template #folder-actions="{ node }">
        <span class="node-actions">
          <a-tooltip v-if="userStore.hasPermission('component:write') && node.depth < 3" content="新建子文件夹">
            <span class="node-action" @click.stop="startNewFolder(node.folderType, node.id)">⊞</span>
          </a-tooltip>
          <a-tooltip v-if="userStore.hasPermission('component:write')" content="新建组件">
            <span class="node-action" @click.stop="newBlankTab(node.folderType as Language, node.id)">＋</span>
          </a-tooltip>
          <a-tooltip v-if="userStore.hasPermission('component:write')" content="删除文件夹">
            <span class="node-action danger" @click.stop="deleteFolder(node.id)">×</span>
          </a-tooltip>
        </span>
      </template>

      <!-- 组件名称（支持重命名 + datax 特殊显示） -->
      <template #comp-name="{ node }">
        <span v-if="renamingCompId !== node.id" class="ftp-name">
          <template v-if="node.data?.type === 'datax' && node.data?.config_json?.source_table">
            {{ node.data.config_json.source_table }} → {{ node.data.config_json.target_table }}
          </template>
          <template v-else>{{ node.name }}</template>
        </span>
        <a-input
          v-else
          v-model="renameCompValue"
          size="mini"
          class="rename-input"
          @blur="submitRenameComp(node.id)"
          @keyup.enter="submitRenameComp(node.id)"
          @keyup.escape="renamingCompId = null"
          @dragstart.stop.prevent
          ref="renameCompInputRef"
        />
      </template>

      <!-- 组件状态圆点 -->
      <template #comp-suffix="{ node }">
        <a-tooltip :content="statusLabel(node.data?.status)" position="right">
          <span
            class="status-dot-only"
            :style="{ background: statusColor(node.data?.status) }"
          ></span>
        </a-tooltip>
      </template>
    </FileTreePanel>

    <!-- 右侧编辑区 -->
    <div class="ide-main">
      <!-- 代码编辑器区域 -->
      <template v-if="tabs.length === 0">
        <div class="ide-empty">
          <div class="empty-hint">从左侧选择组件，或新建</div>
          <a-button type="outline" size="small" @click="newBlankTab('sql')">
            <template #icon><icon-plus /></template>
            新建 SQL
          </a-button>
        </div>
      </template>

      <template v-else>
        <!-- 标签栏 -->
        <div class="tab-bar">
          <div class="tabs-scroll">
            <div
              v-for="tab in tabs"
              :key="tab.key"
              :class="['tab-item', { active: activeKey === tab.key }]"
              @click="switchTab(tab.key)"
            >
              <LangIcon :type="tab.language" :size="16" />
              <span class="tab-name">{{ tab.dirty ? '● ' : '' }}{{ tab.name }}</span>
              <span class="tab-close" @click.stop="closeTab(tab.key)">×</span>
            </div>
          </div>
          <a-dropdown trigger="click">
            <a-button type="text" size="mini" class="add-tab-btn"><icon-plus /></a-button>
            <template #content>
              <a-doption @click="newBlankTab('sql')">新建 SQL</a-doption>
              <a-doption @click="newBlankTab('python')">新建 Python</a-doption>
              <a-doption @click="newBlankTab('shell')">新建 Shell</a-doption>
              <a-doption @click="newBlankTab('datax')">新建 DataX 同步</a-doption>
            </template>
          </a-dropdown>
        </div>

        <!-- DataX 同步任务面板（当前 tab 是 datax 类型时显示） -->
        <template v-if="activeTab && activeTab.language === 'datax'">
          <SyncTaskCanvas
            :task-id="activeTab.syncTaskId ?? null"
            :projects="projects"
            @saved="onDataxSaved"
            style="flex: 1; overflow: auto;"
          />
        </template>

        <!-- 代码编辑器（非 datax tab） -->
        <template v-else-if="activeTab">
          <!-- 工具栏 -->
          <div class="ide-toolbar">
            <a-select
              v-if="activeTab.language === 'sql'"
              v-model="activeTab.datasourceId"
              size="small"
              placeholder="选择数据源"
              style="width: 200px"
            >
              <a-option v-for="ds in datasources" :key="ds.id" :value="ds.id">{{ ds.name }}</a-option>
            </a-select>
            <a-tooltip v-if="activeTab.language === 'sql'" content="格式化 SQL" position="bottom">
              <a-button size="small" @click="formatSQL">
                <template #icon><icon-code-block /></template>
              </a-button>
            </a-tooltip>
            <div style="flex:1" />
            <a-space size="small">
              <a-button v-if="userStore.hasPermission('component:write')" size="small" type="primary" :loading="running" @click="runCode">
                <template #icon><icon-play-arrow /></template>
                运行
              </a-button>
              <a-button v-if="userStore.hasPermission('component:write')" size="small" :loading="saving" @click="saveTab">
                <template #icon><icon-save /></template>
                保存
              </a-button>
              <a-button v-if="activeTab.componentId && userStore.hasPermission('component:publish')" size="small" @click="quickPublish">
                <template #icon><icon-upload /></template>
                发布
              </a-button>
              <a-button size="small" @click="paramsDrawerVisible = true">
                参数{{ activeTab.localParams?.length ? ` (${activeTab.localParams.length})` : '' }}
              </a-button>
            </a-space>
          </div>

          <!-- 编辑器 -->
          <div class="editor-area">
            <CodeEditor
              :key="activeKey"
              :model-value="activeTab ? activeTab.code : ''"
              :language="activeTab ? activeTab.language : 'sql'"
              :datasource-id="activeTab?.datasourceId"
              ref="editorRef"
              height="100%"
              @update:model-value="onCodeChange"
            />
          </div>

          <!-- 结果面板 -->
          <div v-if="result !== null || running" class="result-panel">
            <div class="result-header">
              <span class="result-info">
                <template v-if="running">运行中...</template>
                <template v-else-if="result">
                  <span v-if="result.type === 'table'" class="ok-text">
                    ✓ 共查询到 {{ result.row_count }} 行{{ result.row_count >= 2000 ? '（已达上限，仅展示前 2000 行）' : '' }} · {{ result.duration_ms }}ms
                  </span>
                  <span v-else-if="result.type === 'rowcount'" class="ok-text">✓ 影响 {{ result.affected }} 行 · {{ result.duration_ms }}ms</span>
                  <span v-else-if="result.type === 'log'" :class="result.ok ? 'ok-text' : 'err-text'">
                    {{ result.ok ? '✓' : '✗' }} exit {{ result.exit_code }} · {{ result.duration_ms }}ms
                  </span>
                  <span v-else-if="result.error" class="err-text">✗ {{ result.error }}</span>
                </template>
              </span>
              <a-button type="text" size="mini" @click="result = null">关闭</a-button>
            </div>
            <div class="result-body">
              <div v-if="running" class="result-spin"><a-spin /></div>
              <template v-else-if="result">
                <a-table
                  v-if="result.type === 'table'"
                  :columns="result.columns.map((c: string) => ({ title: c, dataIndex: c, ellipsis: true, width: 120 }))"
                  :data="result.rows"
                  :pagination="{ pageSize: 50, showTotal: true, size: 'mini' }"
                  size="mini"
                  :scroll="{ x: 'max-content' }"
                  class="result-table"
                />
                <div v-else-if="result.type === 'rowcount'" class="result-text ok-text">
                  执行成功，影响 {{ result.affected }} 行
                </div>
                <pre v-else-if="result.type === 'log'" :class="['result-log', result.ok ? 'log-ok' : 'log-err']">{{ result.log }}</pre>
                <div v-else-if="result.error" class="result-text err-text">{{ result.error }}</div>
              </template>
            </div>
          </div>
        </template>
      </template>
    </div>

    <!-- 首次保存弹窗 -->
    <a-modal v-model:visible="saveModalVisible" title="保存组件" @ok="confirmSave" :ok-loading="saving" width="380px">
      <a-form-item label="组件名称">
        <a-input v-model="saveName" placeholder="如：dim_user_query" allow-clear />
      </a-form-item>
    </a-modal>

    <!-- 新建文件夹弹窗 -->
    <a-modal v-model:visible="newFolderVisible" title="新建文件夹" @ok="confirmNewFolder" width="360px">
      <a-form-item label="文件夹名称">
        <a-input v-model="newFolderName" placeholder="如：核心指标" allow-clear />
      </a-form-item>
    </a-modal>

    <!-- 全局右键菜单 -->
    <ContextMenu
      v-model:visible="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :items="contextMenu.items"
      @select="onMenuSelect"
    />

    <!-- 参数编辑抽屉 -->
    <a-drawer
      :visible="paramsDrawerVisible"
      title="组件参数"
      :width="520"
      @cancel="paramsDrawerVisible = false"
      :footer="false"
      unmount-on-close
    >
      <div v-if="activeTab" class="params-editor">
        <div class="params-example-card">
          <div class="params-example-title">使用示例</div>
          <code class="params-example-code">SELECT * FROM orders WHERE dt = ${bizdate} AND type = ${type}</code>
          <div class="params-example-tips">
            <span>1. 在 SQL 中用 <code>${参数名}</code> 引用参数</span>
            <span>2. 无需手动加引号，系统根据参数类型自动处理</span>
            <span>3. 点击"运行"时会自动弹窗填写参数值</span>
          </div>
        </div>
        <div class="params-hint">
          定义组件的参数及类型，运行时会自动检测并弹窗填写。
        </div>
        <div v-for="(p, idx) in (activeTab.localParams || [])" :key="idx" class="param-row">
          <a-input v-model="p.prop" placeholder="参数名" size="small" style="width: 120px;" />
          <a-select v-model="p.direct" size="small" style="width: 80px;">
            <a-option value="IN">IN</a-option>
            <a-option value="OUT">OUT</a-option>
            <a-option value="LOCAL">LOCAL</a-option>
          </a-select>
          <a-select v-model="p.type" size="small" style="width: 110px;">
            <a-option value="VARCHAR">VARCHAR</a-option>
            <a-option value="INTEGER">INTEGER</a-option>
            <a-option value="LONG">LONG</a-option>
            <a-option value="FLOAT">FLOAT</a-option>
            <a-option value="DATE">DATE</a-option>
            <a-option value="TIME">TIME</a-option>
            <a-option value="TIMESTAMP">TIMESTAMP</a-option>
          </a-select>
          <a-input v-model="p.value" placeholder="默认值" size="small" style="flex: 1;" />
          <a-button type="text" size="mini" status="danger" @click="activeTab!.localParams!.splice(idx, 1); activeTab!.dirty = true">
            <template #icon><icon-delete /></template>
          </a-button>
        </div>
        <a-button type="dashed" size="small" long @click="addParam">
          <template #icon><icon-plus /></template>
          添加参数
        </a-button>
      </div>
    </a-drawer>

    <!-- DataX 同步任务向导 -->
    <SyncTaskWizard
      v-model:visible="wizardVisible"
      :projects="projects"
      @saved="loadComponents"
    />

    <!-- 运行参数弹窗 -->
    <SqlParamModal
      v-model:visible="paramModalVisible"
      :params="paramModalParams"
      :sql="paramModalSql"
      @confirm="onParamConfirm"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import LangIcon from '../components/LangIcon.vue'
import FileTreePanel from '../components/FileTreePanel.vue'
import { TYPE_GROUPS_WITH_DATAX, type TreeNode } from '../composables/useFileTree'
import { Message } from '@arco-design/web-vue'
import {
  IconPlus, IconPlayArrow, IconSave, IconUpload, IconDelete, IconCodeBlock,
} from '@arco-design/web-vue/es/icon'
import CodeEditor from '../components/CodeEditor.vue'
import ContextMenu from '../components/ContextMenu.vue'
import type { MenuItem } from '../components/ContextMenu.vue'
import {
  getComponents, createComponent, updateComponent, deleteComponent,
  getDatasources, runSqlAdhoc, runComponentScript, quickPublishComponent,
  getComponentFolders, createComponentFolder, renameComponentFolder, deleteComponentFolder,
  setComponentStatus, resumeComponent,
  moveComponent, reorderComponents, moveComponentFolder,
  getSyncTasks, deleteSyncTask, getProjects,
} from '../api'
import SyncTaskCanvas from '../components/SyncTaskCanvas.vue'
import SyncTaskWizard from '../components/SyncTaskWizard.vue'
import SqlParamModal from '../components/SqlParamModal.vue'
import type { ParamDef } from '../components/SqlParamModal.vue'
import { useUserStore } from '../stores/user'

const userStore = useUserStore()

type Language = 'sql' | 'python' | 'shell' | 'datax'

interface Tab {
  key: string
  name: string
  code: string
  language: Language
  componentId?: number
  folderId?: number | null
  datasourceId?: number
  syncTaskId?: number | null
  localParams?: { prop: string; direct: string; type: string; value: string }[]
  dirty: boolean
}

const treeRef = ref<InstanceType<typeof FileTreePanel> | null>(null)

const tabs = ref<Tab[]>([])
const activeKey = ref('')
const activeTab = computed<Tab | null>(() => tabs.value.find(t => t.key === activeKey.value) ?? null)

const components = ref<any[]>([])
const datasources = ref<any[]>([])
const folders = ref<any[]>([])  // flat list from API
const projects = ref<any[]>([])

const editorRef = ref<any>(null)
const running = ref(false)
const saving = ref(false)
const result = ref<any>(null)

// DataX 同步任务向导
const wizardVisible = ref(false)

// 参数抽屉
const paramsDrawerVisible = ref(false)
function addParam() {
  if (!activeTab.value) return
  if (!activeTab.value.localParams) activeTab.value.localParams = []
  activeTab.value.localParams.push({ prop: '', direct: 'IN', type: 'VARCHAR', value: '' })
  activeTab.value.dirty = true
}

// ---- 运行参数弹窗 ----
const paramModalVisible = ref(false)
const paramModalParams = ref<ParamDef[]>([])
const paramModalSql = ref('')

/**
 * 从 SQL 中提取 ${xxx} 参数名（排除注释内的）
 * 按出现顺序返回，去重
 */
function extractSqlParams(sql: string): string[] {
  // 移除单行注释 -- 和块注释 /* */
  const cleaned = sql
    .replace(/--.*$/gm, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
  const matches = cleaned.matchAll(/\$\{(\w+)\}/g)
  const seen = new Set<string>()
  const result: string[] = []
  for (const m of matches) {
    if (!seen.has(m[1])) {
      seen.add(m[1])
      result.push(m[1])
    }
  }
  return result
}

/**
 * 合并 SQL 中发现的参数和已定义的 localParams
 * 按 SQL 中出现顺序排列，未在 SQL 中出现但已定义的参数追加在后
 */
function mergeParams(sqlParamNames: string[], localParams: Tab['localParams']): ParamDef[] {
  const defMap = new Map<string, { type: string; value: string; direct: string }>()
  for (const p of (localParams || [])) {
    if (p.prop) defMap.set(p.prop, { type: p.type, value: p.value, direct: p.direct })
  }

  const result: ParamDef[] = []
  const seen = new Set<string>()

  // 按 SQL 出现顺序
  for (const name of sqlParamNames) {
    const def = defMap.get(name)
    result.push({
      prop: name,
      type: def?.type || 'VARCHAR',
      value: def?.value || '',
      direct: def?.direct || 'IN',
    })
    seen.add(name)
  }

  // 追加已定义但未在 SQL 中出现的 IN 参数
  for (const p of (localParams || [])) {
    if (p.prop && !seen.has(p.prop) && p.direct === 'IN') {
      result.push({ prop: p.prop, type: p.type, value: p.value, direct: p.direct })
    }
  }

  return result
}

const saveModalVisible = ref(false)
const saveName = ref('')
const pendingSaveTab = ref<Tab | null>(null)

const newFolderVisible = ref(false)
const newFolderName = ref('')
const newFolderContext = ref<{ type: string; parentId: number | null } | null>(null)

const renamingFolderId = ref<number | null>(null)
const renameValue = ref('')
const renameInputRef = ref<any>(null)

// ---- 右键菜单 ----
const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  items: [] as MenuItem[],
})

// ---- 剪贴板 ----
const clipboard = ref<{ kind: 'component' | 'folder'; action: 'copy' | 'cut'; id: number; type?: string; folderType?: string } | null>(null)

// ---- 拖拽 ----
const dragState = reactive({
  draggingId: null as number | null,
  dragKind: null as 'component' | 'folder' | null,
  dragFolderType: null as string | null,
  dragFolderId: null as number | null,
  dropTargetId: null as number | string | null,
  dropKind: null as 'component' | 'folder' | 'group' | null,
  dropPosition: null as 'before' | 'after' | 'inside' | null,
})

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
    const src = cfg.source_table || ''
    const dst = cfg.target_table || ''
    const tabName = src && dst ? `${src} → ${dst}` : c.name
    tabs.value.push({
      key,
      name: tabName,
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
  const existing = tabs.value.find(t => t.componentId === c.id)
  if (existing) { switchTab(existing.key); return }
  const key = genKey()
  // code is stored in config_json.sql or config_json.script
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
  const key = genKey()
  const names: Record<string, string> = { sql: 'Untitled SQL', python: 'Untitled Python', shell: 'Untitled Shell' }
  tabs.value.push({ key, name: names[lang] ?? 'Untitled', code: '', language: lang, folderId: folderId ?? null, dirty: false })
  switchTab(key)
}

function switchTab(key: string) { activeKey.value = key; result.value = null }

function onDataxSaved(res: any) {
  // 新建时 res 包含 _component，需要更新当前 tab 的 syncTaskId/componentId
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

function closeTab(key: string) {
  const idx = tabs.value.findIndex(t => t.key === key)
  if (idx === -1) return
  tabs.value.splice(idx, 1)
  if (activeKey.value === key) activeKey.value = tabs.value[Math.max(0, idx - 1)]?.key ?? ''
  result.value = null
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

// ---- 文件夹操作 ----
function startNewFolder(type: string, parentId: number | null) {
  newFolderContext.value = { type, parentId }
  newFolderName.value = ''
  newFolderVisible.value = true
}

async function confirmNewFolder() {
  if (!newFolderName.value.trim()) { Message.warning('请输入文件夹名称'); return }
  const ctx = newFolderContext.value!
  try {
    await createComponentFolder({
      name: newFolderName.value.trim(),
      type: ctx.type,
      parent_id: ctx.parentId,
    })
    newFolderVisible.value = false
    await loadFolders()
  } catch {}
}

function startRename(node: TreeNode) {
  renamingFolderId.value = node.id
  renameValue.value = node.name
  nextTick(() => {
    const el = renameInputRef.value
    if (Array.isArray(el)) el[0]?.focus?.()
    else el?.focus?.()
  })
}

async function submitRename(id: number) {
  if (!renameValue.value.trim()) { renamingFolderId.value = null; return }
  try {
    await renameComponentFolder(id, renameValue.value.trim())
    await loadFolders()
  } catch {} finally {
    renamingFolderId.value = null
  }
}

async function deleteFolder(id: number) {
  try {
    await deleteComponentFolder(id)
    await loadFolders()
    Message.success('文件夹已删除')
  } catch {}
}

// ---- 状态系统 ----
// 状态定义：自动状态（不可手动设置）+ 手动状态
const STATUS_DEFS: Record<string, { label: string; color: string; manual: boolean }> = {
  draft:       { label: '草稿',   color: '#86909C', manual: false },
  developing:  { label: '开发中', color: '#2B5AED', manual: true  },
  testing:     { label: '测试中', color: '#FF7D00', manual: true  },
  reviewing:   { label: '审核中', color: '#14B8A6', manual: true  },
  tested:      { label: '已测试', color: '#A3C644', manual: true  },
  online:      { label: '已上线', color: '#00B42A', manual: false },
  offline:     { label: '已下线', color: '#C9CDD4', manual: true  },
  paused:      { label: '已暂停', color: '#F53F3F', manual: true  },
  deprecated:  { label: '已废弃', color: '#6B7280', manual: true  },
  archived:    { label: '已归档', color: '#722ED1', manual: true  },
}

function statusLabel(s: string): string {
  return STATUS_DEFS[s]?.label || s
}
function statusColor(s: string): string {
  return STATUS_DEFS[s]?.color || '#86909C'
}
function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.substring(0, 2), 16)
  const g = parseInt(h.substring(2, 4), 16)
  const b = parseInt(h.substring(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
function statusTagStyle(s: string) {
  const color = statusColor(s)
  return {
    background: hexToRgba(color, 0.12),
    color: color,
  }
}
const STATUS_TRANSITIONS: Record<string, string[]> = {
  draft:      ['developing', 'testing', 'deprecated', 'archived'],
  developing: ['testing', 'paused', 'deprecated'],
  testing:    ['reviewing', 'tested', 'paused', 'deprecated'],
  reviewing:  ['tested', 'paused', 'developing'],
  tested:     ['paused', 'testing'],
  online:     ['offline', 'paused'],
  offline:    ['online', 'archived', 'paused', 'developing'],
  paused:     [],
  deprecated: ['archived'],
  archived:   [],
}
function manualStatusOptions(current: string) {
  if (current === 'paused') return []
  if (current === 'archived') return []
  const allowed = STATUS_TRANSITIONS[current] ?? []
  return allowed
    .filter(k => STATUS_DEFS[k]?.manual)
    .map(k => ({ value: k, label: STATUS_DEFS[k].label, color: STATUS_DEFS[k].color }))
}

async function setCompStatus(c: any, status: string) {
  try {
    if (status === '__resume__') {
      await resumeComponent(c.id)
      Message.success('已从暂停恢复')
    } else {
      await setComponentStatus(c.id, status)
      Message.success('状态已更新')
    }
    await loadComponents()
  } catch {}
}

async function confirmDeleteComp(c: any) {
  if (!confirm(`确定删除组件「${c.name}」？此操作不可恢复`)) return
  try {
    if (c.type === 'datax') {
      // 后端 delete_task 会级联删除关联的 Component 和 Workflow
      const syncTaskId = c.config_json?.sync_task_id
      if (syncTaskId) {
        await deleteSyncTask(syncTaskId)
      } else {
        await deleteComponent(c.id)
      }
    } else {
      await deleteComponent(c.id)
    }
    Message.success('已删除')
    const idx = tabs.value.findIndex(t => t.componentId === c.id)
    if (idx >= 0) closeTab(tabs.value[idx].key)
    await loadComponents()
  } catch {}
}

// Convert list-of-lists rows to list-of-objects for a-table
function normalizeResult(res: any): any {
  if (res?.type === 'table' && Array.isArray(res.rows) && Array.isArray(res.columns)) {
    const cols: string[] = res.columns
    res.rows = res.rows.map((row: any[]) =>
      Array.isArray(row) ? Object.fromEntries(cols.map((c, i) => [c, row[i]])) : row
    )
  }
  return res
}

// ---- 运行 ----
async function runCode() {
  const tab = activeTab.value
  if (!tab) return

  if (tab.language === 'sql') {
    if (!tab.datasourceId) { Message.warning('请先选择数据源'); return }
    const sel: string = editorRef.value?.getSelectedText?.() ?? ''
    const sql = (sel || tab.code).trim()
    if (!sql) { Message.warning('请输入 SQL'); return }

    // 提取 SQL 中的参数
    const sqlParamNames = extractSqlParams(sql)
    const merged = mergeParams(sqlParamNames, tab.localParams)

    if (merged.length > 0) {
      // 有参数 → 弹窗填值
      paramModalSql.value = sql
      paramModalParams.value = merged
      paramModalVisible.value = true
      return
    }

    // 无参数 → 直接执行
    await executeSQL(tab, sql)
  } else {
    // Python/Shell 组件
    if (!tab.componentId) { Message.warning('请先保存后再运行'); return }
    result.value = null
    running.value = true
    try {
      if (tab.dirty) await doSave(tab)
      result.value = normalizeResult(await runComponentScript(tab.componentId!, tab.datasourceId))
    } catch (e: any) {
      result.value = { error: e?.response?.data?.detail || '执行失败' }
    } finally {
      running.value = false
    }
  }
}

/** 参数弹窗确认后执行 */
async function onParamConfirm(values: Record<string, string>) {
  const tab = activeTab.value
  if (!tab) return

  // 构建参数类型映射
  const typeMap = new Map<string, string>()
  for (const p of paramModalParams.value) {
    typeMap.set(p.prop, p.type)
  }

  // 替换 SQL 中的 ${param_name}，根据类型自动处理引号
  // 先处理用户已手动加引号的情况 '${xxx}'，再处理裸 ${xxx}
  let sql = paramModalSql.value
  for (const [key, val] of Object.entries(values)) {
    const pType = typeMap.get(key) || 'VARCHAR'
    const needsQuote = ['VARCHAR', 'DATE', 'TIME', 'TIMESTAMP'].includes(pType)
    const quotedVal = needsQuote ? `'${val}'` : val

    // 先替换已被引号包裹的 '${xxx}' → 直接用带引号的值（避免双引号）
    sql = sql.split("'${" + key + "}'").join(quotedVal)
    // 再替换裸 ${xxx} → 也加引号
    sql = sql.split('${' + key + '}').join(quotedVal)
  }

  await executeSQL(tab, sql)
}

/** 实际执行 SQL */
async function executeSQL(tab: Tab, sql: string) {
  result.value = null
  running.value = true
  try {
    result.value = normalizeResult(await runSqlAdhoc({ datasource_id: tab.datasourceId!, sql }))
  } catch (e: any) {
    result.value = { error: e?.response?.data?.detail || '执行失败' }
  } finally {
    running.value = false
  }
}

// ---- 保存 ----
async function saveTab() {
  const tab = activeTab.value
  if (!tab) return
  if (!tab.componentId) {
    // 弹窗已打开时不覆盖，避免丢失正在命名的另一个标签
    if (saveModalVisible.value) {
      Message.warning('请先完成当前保存操作')
      return
    }
    pendingSaveTab.value = tab
    saveName.value = tab.name.startsWith('Untitled') ? '' : tab.name
    saveModalVisible.value = true
    return
  }
  await doSave(tab)
}

async function confirmSave() {
  if (!saveName.value.trim()) { Message.warning('请输入组件名称'); return }
  const tab = pendingSaveTab.value
  if (!tab) return
  tab.name = saveName.value.trim()
  await doSave(tab)
  saveModalVisible.value = false
  pendingSaveTab.value = null
}

async function doSave(tab: Tab) {
  saving.value = true
  try {
    // 构造 config_json
    const langKey = tab.language === 'sql' ? 'sql' : 'script'
    const config_json: any = { [langKey]: tab.code }
    if (tab.datasourceId != null) config_json.datasource_id = tab.datasourceId
    if (tab.localParams?.length) config_json.localParams = tab.localParams

    const payload: any = {
      name: tab.name,
      type: tab.language,
      config_json,
      folder_id: tab.folderId ?? null,
    }
    if (tab.componentId) {
      await updateComponent(tab.componentId, payload)
    } else {
      const res: any = await createComponent(payload)
      tab.componentId = res.id
    }
    tab.dirty = false
    Message.success('已保存')
    await loadComponents()
  } catch {} finally {
    saving.value = false
  }
}

async function quickPublish() {
  const tab = activeTab.value
  if (!tab?.componentId) return
  if (tab.dirty) await doSave(tab)
  try {
    await quickPublishComponent(tab.componentId!)
    Message.success('已发布上线')
    await loadComponents()
  } catch {}
}

// ---- 数据加载 ----
async function loadFolders() {
  try {
    const res: any = await getComponentFolders()
    folders.value = res || []
  } catch {}
}

async function loadComponents() {
  try {
    const res: any = await getComponents({ page_size: 500 })
    components.value = res.items || []
  } catch {}
}

async function loadDatasources() {
  try {
    const res: any = await getDatasources({ page_size: 100 })
    datasources.value = res.items || []
    // Clear stale datasourceId on any open tabs
    const validIds = new Set(datasources.value.map((d: any) => d.id))
    tabs.value.forEach(t => {
      if (t.datasourceId != null && !validIds.has(t.datasourceId)) {
        t.datasourceId = undefined
      }
    })
  } catch {}
}

async function loadProjects() {
  try {
    const res: any = await getProjects({ page_size: 200 })
    projects.value = res.items || res || []
  } catch {}
}

// ---- 右键菜单 ----
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
  if (clipboard.value && clipboard.value.kind === 'component') {
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
  items.push({ divider: true })
  items.push({ key: 'delete', label: '删除', danger: true })
  return items
}

function buildFolderMenuItems(node: TreeNode): MenuItem[] {
  const items: MenuItem[] = []
  const collapsed = folderCollapsed[node.id]
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
  if (clipboard.value && clipboard.value.kind === 'folder') {
    items.push({ key: 'paste', label: '粘贴' })
  }
  items.push({ divider: true })
  items.push({ key: 'delete', label: '删除', danger: true })
  return items
}

function buildStatusSubmenu(current: string): MenuItem[] {
  const opts = manualStatusOptions(current)
  return opts.map(o => ({
    key: `status-${o.value}`,
    label: o.label,
    icon: 'dot',
  }))
}

function buildMoveToFolderMenu(type: string, prefix: string): MenuItem[] {
  const typeFolders = folders.value.filter(f => f.type === type)
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
  // 添加"无文件夹"选项
  menu.unshift({ key: `${prefix}-0`, label: '（无文件夹）' })
  return menu
}

async function onMenuSelect(key: string) {
  // 从 contextMenu 的触发源中恢复当前节点 —— 通过最后一个右键事件记录
  const targetNode = lastContextNode.value
  if (!targetNode) return

  if (key === 'open') {
    if (targetNode.kind === 'component') openComp(targetNode.data)
  } else if (key === 'run') {
    if (targetNode.kind === 'component') {
      openComp(targetNode.data)
      await nextTick()
      runCode()
    }
  } else if (key === 'expand') {
    folderCollapsed[targetNode.id] = false
  } else if (key === 'collapse') {
    folderCollapsed[targetNode.id] = true
  } else if (key === 'copy') {
    if (targetNode.kind === 'component') {
      clipboard.value = { kind: 'component', action: 'copy', id: targetNode.id, type: targetNode.data.type }
    }
  } else if (key === 'cut') {
    if (targetNode.kind === 'component') {
      clipboard.value = { kind: 'component', action: 'cut', id: targetNode.id, type: targetNode.data.type }
    } else if (targetNode.kind === 'folder') {
      clipboard.value = { kind: 'folder', action: 'cut', id: targetNode.id, folderType: targetNode.folderType }
    }
  } else if (key === 'paste') {
    await doPaste(targetNode)
  } else if (key === 'rename') {
    if (targetNode.kind === 'folder') startRename(targetNode)
    else if (targetNode.kind === 'component') startRenameComponent(targetNode)
  } else if (key === 'delete') {
    if (targetNode.kind === 'component') await confirmDeleteComp(targetNode.data)
    else if (targetNode.kind === 'folder') await deleteFolder(targetNode.id)
  } else if (key === 'new-subfolder') {
    if (targetNode.kind === 'folder') startNewFolder(targetNode.folderType, targetNode.id)
  } else if (key === 'resume') {
    if (targetNode.kind === 'component') await setCompStatus(targetNode.data, '__resume__')
  } else if (key.startsWith('status-')) {
    const status = key.replace('status-', '')
    if (targetNode.kind === 'component') await setCompStatus(targetNode.data, status)
  } else if (key.startsWith('move-to-')) {
    const folderId = parseInt(key.replace('move-to-', ''), 10)
    if (targetNode.kind === 'component') await doMoveComponent(targetNode.data.id, folderId)
  } else if (key.startsWith('new-')) {
    const lang = key.replace('new-', '') as Language
    const folderId = targetNode.kind === 'folder' ? targetNode.id : (targetNode.data?.folder_id ?? null)
    newBlankTab(lang, folderId)
  }
}

const lastContextNode = ref<TreeNode | null>(null)

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

// ---- 剪贴板操作 ----
async function doPaste(targetNode: TreeNode) {
  const cb = clipboard.value
  if (!cb) return
  if (cb.kind === 'component') {
    const targetFolderId = targetNode.kind === 'folder' ? targetNode.id : (targetNode.data?.folder_id ?? null)
    if (cb.action === 'copy') {
      // 复制：创建新组件
      const src = components.value.find(c => c.id === cb.id)
      if (!src) return
      try {
        const res: any = await createComponent({
          name: src.name + '_copy',
          type: src.type,
          description: src.description,
          config_json: src.config_json || {},
          folder_id: targetFolderId,
        })
        Message.success('已复制')
        await loadComponents()
        openComp(res)
      } catch {}
    } else if (cb.action === 'cut') {
      await doMoveComponent(cb.id, targetFolderId ?? 0)
      clipboard.value = null
    }
  } else if (cb.kind === 'folder') {
    if (targetNode.kind !== 'folder') return
    if (cb.action === 'cut') {
      // 防止循环引用：不能把文件夹移动到自身或其子孙
      if (cb.id === targetNode.id || folderContains(cb.id, targetNode.id)) {
        Message.error('不能将文件夹移动到自身或其子文件夹中')
        return
      }
      await doMoveFolder(cb.id, targetNode.id)
      clipboard.value = null
    } else if (cb.action === 'copy') {
      // 复制文件夹：创建同名文件夹（不递归复制内容）
      const src = folders.value.find(f => f.id === cb.id)
      if (!src) return
      try {
        await createComponentFolder({
          name: src.name + '_copy',
          type: src.type,
          parent_id: targetNode.id,
        })
        Message.success('已复制文件夹')
        await loadFolders()
        clipboard.value = null
      } catch {}
    }
  }
}

// ---- 组件重命名 ----
const renamingCompId = ref<number | null>(null)
const renameCompValue = ref('')
const renameCompInputRef = ref<any>(null)

function startRenameComponent(node: TreeNode) {
  renamingCompId.value = node.id
  renameCompValue.value = node.name
  nextTick(() => {
    const el = renameCompInputRef.value
    if (Array.isArray(el)) el[0]?.focus?.()
    else el?.focus?.()
  })
}

async function submitRenameComp(id: number) {
  if (!renameCompValue.value.trim()) { renamingCompId.value = null; return }
  try {
    await updateComponent(id, { name: renameCompValue.value.trim() })
    await loadComponents()
    // 更新已打开 tab 的名称
    const tab = tabs.value.find(t => t.componentId === id)
    if (tab) tab.name = renameCompValue.value.trim()
  } catch {} finally {
    renamingCompId.value = null
  }
}

// ---- 拖拽状态 CSS 映射 ----
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

// ---- 拖拽 ----
function onDragStart(e: DragEvent, node: TreeNode) {
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

function onDragOver(e: DragEvent, targetNode: TreeNode) {
  e.preventDefault()
  // 同节点不处理
  if (dragState.draggingId === targetNode.id) {
    dragState.dropTargetId = null
    dragState.dropKind = null
    dragState.dropPosition = null
    e.dataTransfer!.dropEffect = 'none'
    return
  }

  // 跨类型阻止
  if (dragState.dragFolderType !== targetNode.folderType) {
    dragState.dropTargetId = null
    dragState.dropKind = null
    dragState.dropPosition = null
    e.dataTransfer!.dropEffect = 'none'
    return
  }

  // 文件夹不能拖到组件上
  if (dragState.dragKind === 'folder' && targetNode.kind === 'component') {
    dragState.dropTargetId = null
    dragState.dropKind = null
    dragState.dropPosition = null
    e.dataTransfer!.dropEffect = 'none'
    return
  }

  // 文件夹拖到文件夹：阻止循环引用（不能拖到自身或其子文件夹）
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

  // 计算插入位置：文件夹 = inside，组件 = 根据鼠标位置判断 before/after
  if (targetNode.kind === 'folder') {
    dragState.dropPosition = 'inside'
  } else {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const midY = rect.top + rect.height / 2
    dragState.dropPosition = e.clientY < midY ? 'before' : 'after'
  }
}

async function onDrop(e: DragEvent, targetNode: TreeNode) {
  e.preventDefault()
  const dataStr = e.dataTransfer!.getData('application/json')
  if (!dataStr) return
  const data = JSON.parse(dataStr)

  // 跨类型忽略
  if (dragState.dragFolderType !== targetNode.folderType) return

  if (data.kind === 'component' && targetNode.kind === 'folder') {
    // 组件拖到文件夹 = 移动
    await doMoveComponent(data.id, targetNode.id)
  } else if (data.kind === 'component' && targetNode.kind === 'component') {
    // 组件拖到组件
    if (data.folderId === targetNode.data?.folder_id) {
      // 同文件夹 = 排序
      await doReorderBetween(data.id, targetNode.id, (dragState.dropPosition === 'inside' ? 'before' : dragState.dropPosition) ?? 'before')
    } else {
      // 跨文件夹 = 移到目标文件夹（根目录用 0）
      await doMoveComponent(data.id, targetNode.data?.folder_id ?? 0)
      // 等待数据刷新后再排序
      await loadComponents()
      await doReorderBetween(data.id, targetNode.id, (dragState.dropPosition === 'inside' ? 'before' : dragState.dropPosition) ?? 'before')
    }
  } else if (dragState.dragKind === 'folder' && targetNode.kind === 'folder') {
    // 文件夹拖到文件夹 = 嵌套移动
    if (dragState.draggingId! === targetNode.id || folderContains(dragState.draggingId!, targetNode.id)) return
    await doMoveFolder(data.id, targetNode.id)
  }

  dragState.draggingId = null
  dragState.dragKind = null
  dragState.dragFolderType = null
  dragState.dragFolderId = null
  dragState.dropTargetId = null
  dragState.dropKind = null
  dragState.dropPosition = null
}

/** 拖拽经过类型组标题：只允许同类型组件移回根目录 */
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
  dragState.draggingId = null
  dragState.dragKind = null
  dragState.dragFolderType = null
  dragState.dragFolderId = null
  dragState.dropTargetId = null
  dragState.dropKind = null
  dragState.dropPosition = null
}

function onDragEnd(_e?: DragEvent, _node?: TreeNode) {
  dragState.draggingId = null
  dragState.dragKind = null
  dragState.dragFolderType = null
  dragState.dragFolderId = null
  dragState.dropTargetId = null
  dragState.dropKind = null
  dragState.dropPosition = null
}

async function doMoveComponent(compId: number, folderId: number) {
  try {
    await moveComponent(compId, folderId)
    Message.success('移动成功')
    await loadComponents()
  } catch {}
}

async function doReorderBetween(dragId: number, targetId: number, dropPosition: 'before' | 'after' = 'before') {
  // 获取同文件夹的所有组件，重新计算 sort_order
  const dragComp = components.value.find(c => c.id === dragId)
  const targetComp = components.value.find(c => c.id === targetId)
  if (!dragComp || !targetComp) return
  const sameFolder = components.value
    .filter(c => c.folder_id === targetComp.folder_id && c.type === targetComp.type)
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || b.id - a.id)

  const dragIdx = sameFolder.findIndex(c => c.id === dragId)
  const targetIdx = sameFolder.findIndex(c => c.id === targetId)
  if (dragIdx === -1 || targetIdx === -1) return

  // 移动数组元素，区分 before/after
  const item = sameFolder.splice(dragIdx, 1)[0]
  const insertIdx = dropPosition === 'after'
    ? (dragIdx < targetIdx ? targetIdx : targetIdx + 1)
    : (dragIdx > targetIdx ? targetIdx : targetIdx)
  sameFolder.splice(insertIdx, 0, item)

  // 重新分配 sort_order
  const orders = sameFolder.map((c, i) => ({ id: c.id, sort_order: i * 10 }))
  try {
    await reorderComponents(orders)
    await loadComponents()
  } catch {}
}

async function doMoveFolder(folderId: number, parentId: number) {
  try {
    await moveComponentFolder(folderId, parentId)
    Message.success('移动成功')
    await loadFolders()
  } catch {}
}

onMounted(() => Promise.all([loadFolders(), loadComponents(), loadDatasources(), loadProjects()]))
</script>

<style scoped>
.ide-wrap {
  display: flex;
  height: calc(100vh - 110px);
  background: var(--color-bg-surface);
  border-radius: 10px;
  overflow: hidden;
  box-shadow: var(--shadow-card);
}

/* ---- 左侧（FileTreePanel 容器） ---- */
.ide-sidebar { width: 280px; flex-shrink: 0; }
.ide-sidebar :deep(.ftp) { height: 100%; }

/* 右键菜单中的状态圆点 */
.opt-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 8px;
  vertical-align: middle;
}
.opt-danger { color: var(--color-danger) !important; }
.opt-danger:hover { background: var(--color-danger-light) !important; }

/* ---- 右侧 ---- */
.ide-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.ide-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--color-text-tertiary);
}
.empty-hint { font-size: 14px; }

/* Tab bar */
.tab-bar {
  display: flex;
  align-items: center;
  height: 38px;
  background: var(--color-bg-base);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
  overflow: hidden;
}
.tabs-scroll {
  display: flex;
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  height: 100%;
  scrollbar-width: none;
}
.tabs-scroll::-webkit-scrollbar { display: none; }
.tab-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  height: 100%;
  white-space: nowrap;
  cursor: pointer;
  font-size: 13px;
  color: var(--color-text-secondary);
  border-right: 1px solid var(--color-border);
  flex-shrink: 0;
  transition: background 0.1s;
}
.tab-item:hover { background: var(--color-primary-light); }
.tab-item.active { background: var(--color-bg-surface); color: var(--color-primary); border-bottom: 2px solid var(--color-primary); }
.tab-name { max-width: 140px; overflow: hidden; text-overflow: ellipsis; }
.tab-close {
  width: 16px; height: 16px;
  line-height: 14px;
  text-align: center;
  border-radius: 50%;
  font-size: 14px;
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}
.tab-close:hover { background: var(--color-danger); color: var(--color-text-inverse); }

.add-tab-btn { flex-shrink: 0; margin: 0 4px; }

/* Toolbar */
.ide-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-surface);
  flex-shrink: 0;
}

/* Editor */
.editor-area { flex: 1; min-height: 0; overflow: hidden; }

/* Result panel */
.result-panel {
  max-height: 360px;
  flex-shrink: 0;
  border-top: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  background: var(--color-bg-surface);
}
.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 14px;
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-base);
  font-size: 13px;
  flex-shrink: 0;
}
.result-info { font-size: 13px; color: var(--color-text-secondary); }
.ok-text { color: var(--color-success); font-weight: 500; }
.err-text { color: var(--color-danger); font-weight: 500; }
.result-body { flex: 1; min-height: 0; overflow: auto; }
.result-spin { display: flex; align-items: center; justify-content: center; padding: 40px; }
.result-table { font-size: 12px; }
.result-text { padding: 16px; font-size: 13px; }
.result-log {
  margin: 0; padding: 12px 14px;
  font-size: 12px;
  font-family: var(--font-family-mono);
  white-space: pre-wrap; word-break: break-all; line-height: 1.6;
}
.log-ok { color: var(--color-text-primary); }
.log-err { color: var(--color-danger); }

/* 参数编辑器 */
.params-editor { display: flex; flex-direction: column; gap: 12px; }
.params-example-card {
  padding: 12px 14px;
  background: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
}
.params-example-title {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-primary);
  margin-bottom: 6px;
}
.params-example-code {
  display: block;
  padding: 6px 10px;
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-family: var(--font-family-mono);
  font-size: 11px;
  color: var(--color-primary);
  white-space: pre-wrap;
  word-break: break-all;
  margin-bottom: 8px;
}
.params-example-tips {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: var(--color-text-secondary);
  line-height: 1.6;
}
.params-example-tips code {
  background: var(--color-bg-base);
  padding: 1px 4px;
  border-radius: 3px;
  font-family: var(--font-family-mono);
  font-size: 11px;
}
.params-hint { font-size: 12px; color: var(--color-text-tertiary); line-height: 1.6; padding: 10px 12px; background: var(--color-bg-elevated); border-radius: var(--radius-md); }
.param-row { display: flex; align-items: center; gap: 8px; }
</style>
