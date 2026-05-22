<template>
  <div class="ide-wrap">
    <!-- 左侧文件夹树 -->
    <div class="ide-sidebar" :style="{ width: sidebarWidth + 'px' }">
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
        <a-tooltip v-if="userStore.hasPermission('component:write')" content="导入组件">
          <span class="grp-action" @click.stop="importModalVisible = true">⇧</span>
        </a-tooltip>
        <a-tooltip v-if="userStore.hasPermission('component:write')" content="新建文件夹">
          <span class="grp-action" @click.stop="startNewFolder(group.type, null)">⊞</span>
        </a-tooltip>
        <a-tooltip v-if="userStore.hasPermission('component:write')" content="请在文件夹内新建组件">
          <span class="grp-action" style="opacity:0.4;cursor:not-allowed">＋</span>
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

      <!-- 组件名称（支持重命名） -->
      <template #comp-name="{ node }">
        <span v-if="renamingCompId !== node.id" class="ftp-name" @dblclick.stop="startRenameComponent(node)">{{ node.name }}</span>
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
    </div>
    <div class="resize-handle" :class="{ active: sidebarDragging }" @mousedown="onSidebarMouseDown"></div>

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
          <div ref="tabsScrollRef" class="tabs-scroll">
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
          <a-dropdown v-if="overflowTabs.length > 0" trigger="click">
            <a-button type="text" size="mini" class="overflow-btn">
              <icon-more />
              <span style="font-size: 11px; margin-left: 2px;">+{{ overflowTabs.length }}</span>
            </a-button>
            <template #content>
              <a-doption v-for="tab in overflowTabs" :key="tab.key" @click="switchTab(tab.key)">
                <LangIcon :type="tab.language" :size="14" style="margin-right: 6px;" />
                {{ tab.dirty ? '● ' : '' }}{{ tab.name }}
              </a-doption>
            </template>
          </a-dropdown>
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
            :locked="currentLockState().locked"
            :locked-by-me="currentLockState().lockedByMe"
            @saved="onDataxSaved"
            style="flex: 1; overflow: auto;"
          />
        </template>

        <!-- 代码编辑器（非 datax tab） -->
        <template v-else-if="activeTab">
          <!-- 锁定提示 -->
          <div v-if="currentLockState().locked && !currentLockState().lockedByMe" class="lock-bar">
            <icon-lock style="font-size: 14px;" />
            <span>该组件正在被其他用户编辑，当前为只读模式</span>
          </div>
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
            <!-- 存储过程类型：渲染配置表单代替代码编辑器 -->
            <div v-if="activeTab.language === 'procedure'" class="proc-form">
              <a-form :model="activeTab.procedure" auto-label-width layout="vertical">
                <a-form-item label="数据源">
                  <a-select
                    v-model="activeTab.datasourceId"
                    placeholder="选择执行存储过程的数据库"
                    @change="markDirty"
                  >
                    <a-option v-for="ds in datasources" :key="ds.id" :value="ds.id">
                      {{ ds.name }} ({{ ds.type }})
                    </a-option>
                  </a-select>
                </a-form-item>
                <a-form-item label="存储过程名">
                  <a-input
                    v-model="activeTab.procedure!.procedure_name"
                    placeholder="如 proc_fby_daily"
                    @input="markDirty"
                  />
                </a-form-item>
                <a-form-item label="参数列表">
                  <div style="width:100%">
                    <div
                      v-for="(_, idx) in activeTab.procedure!.params"
                      :key="idx"
                      style="display:flex;gap:8px;margin-bottom:6px"
                    >
                      <a-input
                        v-model="activeTab.procedure!.params[idx]"
                        :placeholder="`参数 ${idx + 1} (支持 ${'${'}bizdate})`"
                        @input="markDirty"
                      />
                      <a-button type="text" status="danger" size="small" @click="removeProcParam(idx)">删除</a-button>
                    </div>
                    <a-button size="small" @click="addProcParam">＋ 增加参数</a-button>
                  </div>
                </a-form-item>
                <a-form-item label="超时(秒)">
                  <a-input-number
                    v-model="activeTab.procedure!.timeout"
                    :min="1"
                    :max="86400"
                    @change="markDirty"
                  />
                </a-form-item>
                <div style="color:var(--color-text-3);font-size:12px">
                  参数中可使用 <code>${'${'}bizdate}</code>、<code>${'${'}bizdatecn}</code> 等占位符，运行时按 run_date 替换。
                </div>
              </a-form>
            </div>
            <CodeEditor
              v-else
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
              <div style="display: flex; align-items: center; gap: 4px;">
                <a-button v-if="result && result.type === 'table'" type="text" size="mini" @click="exportToExcel">
                  <template #icon><icon-download /></template>
                  导出Excel
                </a-button>
                <a-button type="text" size="mini" @click="result = null">关闭</a-button>
              </div>
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

      <!-- 右侧 Activity Bar -->
      <div class="right-bar">
        <a-tooltip content="基本信息" position="left">
          <div :class="['rbar-icon', { active: activeRightPanel === 'info' }]" @click="toggleRightPanel('info')">
            <icon-info-circle />
          </div>
        </a-tooltip>
        <a-tooltip content="参数配置" position="left">
          <div :class="['rbar-icon', { active: activeRightPanel === 'params' }]" @click="toggleRightPanel('params')">
            <icon-settings />
          </div>
        </a-tooltip>
        <a-tooltip content="环境参数" position="left">
          <div :class="['rbar-icon', { active: activeRightPanel === 'env' }]" @click="toggleRightPanel('env')">
            <icon-thunderbolt />
          </div>
        </a-tooltip>
        <a-tooltip content="操作记录" position="left">
          <div :class="['rbar-icon', { active: activeRightPanel === 'history' }]" @click="toggleRightPanel('history')">
            <icon-history />
          </div>
        </a-tooltip>
      </div>

      <!-- 右侧展开面板 -->
      <transition name="slide-right">
        <div v-if="activeRightPanel" class="right-panel">
          <div class="rpanel-header">
            <span>{{ rightPanelTitle }}</span>
            <a-button type="text" size="mini" @click="activeRightPanel = null">×</a-button>
          </div>
          <div class="rpanel-body">
            <!-- 基本信息 -->
            <template v-if="activeRightPanel === 'info' && activeTab">
              <div class="rpanel-field"><label>名称</label><span>{{ activeTab.name }}</span></div>
              <div class="rpanel-field"><label>类型</label><span>{{ activeTab.language }}</span></div>
              <div class="rpanel-field"><label>状态</label><span>{{ activeTab.componentId ? statusLabel(components.find(c => c.id === activeTab!.componentId)?.status || 'draft') : '未保存' }}</span></div>
              <div class="rpanel-field"><label>创建时间</label><span>{{ components.find(c => c.id === activeTab!.componentId)?.created_at || '-' }}</span></div>
              <div class="rpanel-field"><label>更新时间</label><span>{{ components.find(c => c.id === activeTab!.componentId)?.updated_at || '-' }}</span></div>
            </template>
            <div v-else-if="activeRightPanel === 'info'" class="rpanel-empty">请先打开组件</div>

            <!-- 参数配置 -->
            <template v-if="activeRightPanel === 'params' && activeTab">
              <div class="rpanel-hint">在 SQL 中用 <code>${参数名}</code> 引用</div>
              <div v-for="(p, idx) in (activeTab.localParams || [])" :key="idx" class="param-row-mini">
                <a-input v-model="p.prop" placeholder="参数名" size="mini" style="width: 90px;" />
                <a-select v-model="p.type" size="mini" style="width: 90px;">
                  <a-option value="VARCHAR">VARCHAR</a-option>
                  <a-option value="INTEGER">INTEGER</a-option>
                  <a-option value="DATE">DATE</a-option>
                </a-select>
                <a-input v-model="p.value" placeholder="默认值" size="mini" style="width: 80px;" />
                <a-button type="text" size="mini" status="danger" @click="activeTab!.localParams!.splice(idx, 1)">×</a-button>
              </div>
              <a-button size="mini" type="dashed" long @click="addParam">+ 添加参数</a-button>
            </template>
            <div v-else-if="activeRightPanel === 'params'" class="rpanel-empty">请先打开组件</div>

            <!-- 环境参数 -->
            <template v-if="activeRightPanel === 'env' && activeTab">
              <div class="rpanel-field">
                <label>数据源</label>
                <a-select v-model="activeTab.datasourceId" size="small" placeholder="选择数据源" allow-clear>
                  <a-option v-for="ds in datasources" :key="ds.id" :value="ds.id">{{ ds.name }}</a-option>
                </a-select>
              </div>
              <div class="rpanel-field">
                <label>超时(秒)</label>
                <a-input-number v-model="(activeTab as any).timeout" size="small" :min="0" :max="7200" placeholder="默认不限" style="width: 100%;" />
              </div>
            </template>
            <div v-else-if="activeRightPanel === 'env'" class="rpanel-empty">请先打开组件</div>

            <!-- 操作记录 -->
            <template v-if="activeRightPanel === 'history' && activeTab?.componentId">
              <div class="rpanel-field"><label>最近更新</label><span>{{ components.find(c => c.id === activeTab!.componentId)?.updated_at || '-' }}</span></div>
              <div class="rpanel-field"><label>创建时间</label><span>{{ components.find(c => c.id === activeTab!.componentId)?.created_at || '-' }}</span></div>
              <div class="rpanel-hint" style="margin-top: 12px;">更多版本历史功能开发中...</div>
            </template>
            <div v-else-if="activeRightPanel === 'history'" class="rpanel-empty">请先保存组件</div>
          </div>
        </div>
      </transition>
    </div>

    <!-- 首次保存弹窗 -->
    <a-modal v-model:visible="saveModalVisible" title="保存组件" @ok="confirmSave" :ok-loading="saving" width="380px">
      <a-form-item label="组件名称">
        <a-input v-model="saveName" placeholder="如：dim_user_query" allow-clear />
      </a-form-item>
      <a-form-item label="所属文件夹">
        <a-select v-model="saveFolderId" placeholder="请选择文件夹（必填）" allow-clear style="width:100%">
          <a-option
            v-for="f in folders.filter(f => f.type === pendingSaveTab?.language || f.type === (pendingSaveTab?.language === 'datax' ? 'datax' : pendingSaveTab?.language))"
            :key="f.id"
            :value="f.id"
          >{{ f.name }}</a-option>
        </a-select>
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

    <!-- 导入组件弹窗 -->
    <ImportModal
      v-model:visible="importModalVisible"
      @imported="loadComponents"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import LangIcon from '../components/LangIcon.vue'
import FileTreePanel from '../components/FileTreePanel.vue'
import { TYPE_GROUPS_WITH_DATAX, type TreeNode } from '../composables/useFileTree'
import { Message } from '@arco-design/web-vue'
import {
  IconPlus, IconPlayArrow, IconSave, IconUpload, IconDelete, IconCodeBlock, IconMore,
  IconInfoCircle, IconSettings, IconThunderbolt, IconHistory, IconDownload,
} from '@arco-design/web-vue/es/icon'
import CodeEditor from '../components/CodeEditor.vue'
import ContextMenu from '../components/ContextMenu.vue'
import {
  getComponents, createComponent, updateComponent, deleteComponent,
  getDatasources, runSqlAdhoc, runComponentScript, quickPublishComponent,
  getComponentFolders, createComponentFolder, renameComponentFolder, deleteComponentFolder,
  setComponentStatus, resumeComponent,
  deleteSyncTask, getProjects,
  exportComponents,
  lockComponent, unlockComponent, lockSyncTask, unlockSyncTask,
} from '../api'
import SyncTaskCanvas from '../components/SyncTaskCanvas.vue'
import SyncTaskWizard from '../components/SyncTaskWizard.vue'
import SqlParamModal from '../components/SqlParamModal.vue'
import ImportModal from '../components/ImportModal.vue'
import type { ParamDef } from '../utils/sqlParams'
import { extractSqlParams, mergeParams, substituteSqlParams } from '../utils/sqlParams'
import { useUserStore } from '../stores/user'
import * as XLSX from 'xlsx'

import { useTabs, type Tab, type Language } from '../composables/useTabs'
import { statusLabel, statusColor } from '../composables/useComponentStatus'
import { useComponentDrag } from '../composables/useComponentDrag'
import { useContextMenu } from '../composables/useContextMenu'
import { useResizePanel } from '../composables/useResizePanel'

const userStore = useUserStore()

// 左侧栏拖拽
const { width: sidebarWidth, dragging: sidebarDragging, onMouseDown: onSidebarMouseDown } = useResizePanel('sqldev-sidebar-width', 280, 180, 480)

const treeRef = ref<InstanceType<typeof FileTreePanel> | null>(null)

const components = ref<any[]>([])
const datasources = ref<any[]>([])
const folders = ref<any[]>([])  // flat list from API
const projects = ref<any[]>([])

const running = ref(false)
const saving = ref(false)
const result = ref<any>(null)

// Excel 导出
function exportToExcel() {
  if (!result.value || result.value.type !== 'table') return
  if (result.value.row_count > 10000) {
    Message.info('数据量较大，导出中请稍候...')
  }
  const ws = XLSX.utils.json_to_sheet(result.value.rows, { header: result.value.columns })
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'QueryResult')
  XLSX.writeFile(wb, `query_result_${Date.now()}.xlsx`)
}

// DataX 同步任务向导
const wizardVisible = ref(false)

// ---- Composables ----

const {
  tabs, activeKey, activeTab, editorRef,
  openComp, newBlankTab,
  switchTab: _switchTab,
  closeTab: _closeTab,
  onCodeChange, formatSQL, onDataxSaved,
} = useTabs(components, datasources, loadComponents)

// 包装 switchTab/closeTab 以同时清理 result
function switchTab(key: string) { _switchTab(key); result.value = null }
function closeTab(key: string) {
  // 释放锁
  const tab = tabs.value.find(t => t.key === key)
  if (tab) releaseLock(tab)
  _closeTab(key); result.value = null
}

// ---- 存储过程组件辅助 ----
function markDirty() {
  if (activeTab.value) activeTab.value.dirty = true
}
function addProcParam() {
  if (!activeTab.value?.procedure) return
  activeTab.value.procedure.params.push('')
  activeTab.value.dirty = true
}
function removeProcParam(idx: number) {
  if (!activeTab.value?.procedure) return
  activeTab.value.procedure.params.splice(idx, 1)
  activeTab.value.dirty = true
}

// ---- 编辑锁管理 ----
const lockStates = ref<Record<string, { locked: boolean; lockedByMe: boolean }>>({})

async function acquireLock(tab: Tab) {
  if (!tab.componentId && !tab.syncTaskId) return
  const tabKey = tab.key
  try {
    if (tab.language === 'datax' && tab.syncTaskId) {
      await lockSyncTask(tab.syncTaskId)
    } else if (tab.componentId) {
      await lockComponent(tab.componentId)
    }
    lockStates.value[tabKey] = { locked: true, lockedByMe: true }
  } catch (e: any) {
    if (e?.response?.status === 409) {
      lockStates.value[tabKey] = { locked: true, lockedByMe: false }
      Message.warning(e.response.data?.detail || '组件正在被其他用户编辑')
    }
  }
}

async function releaseLock(tab: Tab) {
  const state = lockStates.value[tab.key]
  if (!state?.lockedByMe) return
  try {
    if (tab.language === 'datax' && tab.syncTaskId) {
      await unlockSyncTask(tab.syncTaskId)
    } else if (tab.componentId) {
      await unlockComponent(tab.componentId)
    }
  } catch {}
  delete lockStates.value[tab.key]
}

function currentLockState() {
  if (!activeTab.value) return { locked: false, lockedByMe: true }
  return lockStates.value[activeTab.value.key] || { locked: false, lockedByMe: true }
}

// ---- Tab 溢出管理 ----
const tabsScrollRef = ref<HTMLElement | null>(null)
const overflowStartIndex = ref(Infinity)

const overflowTabs = computed(() => {
  if (overflowStartIndex.value >= tabs.value.length) return []
  return tabs.value.slice(overflowStartIndex.value)
})

function recalcVisibleTabs() {
  const container = tabsScrollRef.value
  if (!container) return
  const containerWidth = container.clientWidth
  if (containerWidth <= 0) return
  const children = Array.from(container.children) as HTMLElement[]
  let newStart = Infinity
  for (let i = 0; i < children.length; i++) {
    const el = children[i]
    // 如果元素右边缘超出容器宽度，则从这里开始溢出
    if (el.offsetLeft + el.offsetWidth > containerWidth) {
      newStart = i
      break
    }
  }
  overflowStartIndex.value = newStart
}

let tabResizeObserver: ResizeObserver | null = null
onMounted(() => {
  tabResizeObserver = new ResizeObserver(() => {
    nextTick(() => recalcVisibleTabs())
  })
  nextTick(() => {
    if (tabsScrollRef.value) {
      tabResizeObserver!.observe(tabsScrollRef.value)
    }
    recalcVisibleTabs()
  })
})
onUnmounted(() => { tabResizeObserver?.disconnect() })
// 当 tab 数量变化时重新计算溢出
watch(() => tabs.value.length, () => { nextTick(() => recalcVisibleTabs()) })

// ---- 锁: 切换 tab 时自动抢锁 ----
watch(() => activeTab.value?.key, (newKey) => {
  if (!newKey) return
  const tab = tabs.value.find(t => t.key === newKey)
  if (tab && (tab.componentId || tab.syncTaskId) && !lockStates.value[newKey]) {
    acquireLock(tab)
  }
})

// 页面卸载时释放所有锁
function releaseAllLocks() {
  for (const tab of tabs.value) {
    const state = lockStates.value[tab.key]
    if (state?.lockedByMe) {
      if (tab.language === 'datax' && tab.syncTaskId) {
        navigator.sendBeacon(`/api/sync-tasks/${tab.syncTaskId}/unlock`)
      } else if (tab.componentId) {
        navigator.sendBeacon(`/api/components/${tab.componentId}/unlock`)
      }
    }
  }
}
onUnmounted(() => releaseAllLocks())
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', releaseAllLocks)
}

// ---- 右侧面板 ----
const activeRightPanel = ref<string | null>(null)
function toggleRightPanel(panel: string) {
  activeRightPanel.value = activeRightPanel.value === panel ? null : panel
}
const rightPanelTitle = computed(() => {
  const map: Record<string, string> = { info: '基本信息', params: '参数配置', env: '环境参数', history: '操作记录' }
  return map[activeRightPanel.value || ''] || ''
})

const {
  dragState,
  getNodeClass, getFolderClass, getGroupClass,
  onCompDragStart: onDragStart,
  onDragOverNode: onDragOver,
  onDropOnNode: onDrop,
  onDragEnd,
  onDragOverGroup,
  onDropGroup,
  folderContains,
  doMoveComponent,
  doMoveFolder,
} = useComponentDrag(components, folders, loadComponents, loadFolders)

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

const saveModalVisible = ref(false)
const saveName = ref('')
const saveFolderId = ref<number | null>(null)
const pendingSaveTab = ref<Tab | null>(null)

const newFolderVisible = ref(false)
const newFolderName = ref('')
const newFolderContext = ref<{ type: string; parentId: number | null } | null>(null)

const renamingFolderId = ref<number | null>(null)
const renameValue = ref('')
const renameInputRef = ref<any>(null)

// ---- 剪贴板 ----
const clipboard = ref<{ kind: 'component' | 'folder'; action: 'copy' | 'cut'; id: number; type?: string; folderType?: string } | null>(null)

// ---- 导入/导出 ----
const importModalVisible = ref(false)

function downloadJson(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function doExportComponent(c: any) {
  try {
    const res: any = await exportComponents([c.id])
    downloadJson(new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' }), `${c.name || 'component'}.json`)
    Message.success('导出成功')
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '导出失败')
  }
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
  } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
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
  } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') } finally {
    renamingFolderId.value = null
  }
}

async function deleteFolder(id: number) {
  try {
    await deleteComponentFolder(id)
    await loadFolders()
    Message.success('文件夹已删除')
  } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
}

// ---- 状态操作 ----
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
  } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
}

async function confirmDeleteComp(c: any) {
  if (!confirm(`确定删除组件「${c.name}」？此操作不可恢复`)) return
  try {
    if (c.type === 'datax') {
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
  } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
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
    const tab = tabs.value.find(t => t.componentId === id)
    if (tab) tab.name = renameCompValue.value.trim()
  } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') } finally {
    renamingCompId.value = null
  }
}

// ---- 剪贴板操作 ----
async function doPaste(targetNode: TreeNode) {
  const cb = clipboard.value
  if (!cb) return
  if (cb.kind === 'component') {
    const targetFolderId = targetNode.kind === 'folder' ? targetNode.id : (targetNode.data?.folder_id ?? null)
    if (cb.action === 'copy') {
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
      } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
    } else if (cb.action === 'cut') {
      await doMoveComponent(cb.id, targetFolderId ?? 0)
      clipboard.value = null
    }
  } else if (cb.kind === 'folder') {
    if (targetNode.kind !== 'folder') return
    if (cb.action === 'cut') {
      if (cb.id === targetNode.id || folderContains(cb.id, targetNode.id)) {
        Message.error('不能将文件夹移动到自身或其子文件夹中')
        return
      }
      await doMoveFolder(cb.id, targetNode.id)
      clipboard.value = null
    } else if (cb.action === 'copy') {
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
      } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
    }
  }
}

// ---- 右键菜单 ----
const {
  contextMenu,
  onMenuSelect,
  showCompContextMenu,
  showFolderContextMenu,
} = useContextMenu({
  folders,
  clipboard,
  folderCollapsedGetter: (id: number) => !!treeRef.value?.folderCollapsed?.[id],
  folderCollapsedSetter: (id: number, val: boolean) => {
    if (treeRef.value?.folderCollapsed) treeRef.value.folderCollapsed[id] = val
  },
  openComp,
  runCode,
  newBlankTab,
  startRename,
  startRenameComponent,
  startNewFolder,
  confirmDeleteComp,
  deleteFolder,
  setCompStatus,
  doPaste,
  doMoveComponent,
  exportComponent: doExportComponent,
})

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

    const sqlParamNames = extractSqlParams(sql)
    const merged = mergeParams(sqlParamNames, tab.localParams || [])

    if (merged.length > 0) {
      paramModalSql.value = sql
      paramModalParams.value = merged
      paramModalVisible.value = true
      return
    }

    await executeSQL(tab, sql)
  } else {
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

  const typeMap = new Map<string, string>()
  for (const p of paramModalParams.value) {
    typeMap.set(p.prop, p.type)
  }

  const sql = substituteSqlParams(paramModalSql.value, values, typeMap)
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
    if (saveModalVisible.value) {
      Message.warning('请先完成当前保存操作')
      return
    }
    pendingSaveTab.value = tab
    saveName.value = tab.name.startsWith('Untitled') ? '' : tab.name
    saveFolderId.value = tab.folderId ?? null
    saveModalVisible.value = true
    return
  }
  await doSave(tab)
}

async function confirmSave() {
  if (!saveName.value.trim()) { Message.warning('请输入组件名称'); return }
  if (saveFolderId.value == null) { Message.warning('请选择所属文件夹'); return }
  const tab = pendingSaveTab.value
  if (!tab) return
  tab.name = saveName.value.trim()
  tab.folderId = saveFolderId.value
  await doSave(tab)
  saveModalVisible.value = false
  pendingSaveTab.value = null
}

async function doSave(tab: Tab) {
  saving.value = true
  try {
    let config_json: any
    if (tab.language === 'procedure') {
      config_json = {
        datasource_id: tab.datasourceId,
        procedure_name: tab.procedure?.procedure_name || '',
        params: tab.procedure?.params || [],
        timeout: tab.procedure?.timeout ?? 3600,
      }
    } else {
      const langKey = tab.language === 'sql' ? 'sql' : 'script'
      config_json = { [langKey]: tab.code }
      if (tab.datasourceId != null) config_json.datasource_id = tab.datasourceId
      if (tab.localParams?.length) config_json.localParams = tab.localParams
    }

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
  } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') } finally {
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
  } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
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
.ide-sidebar { flex-shrink: 0; overflow: hidden; }
.ide-sidebar :deep(.ftp) { height: 100%; }

/* 拖拽分割条 */
.resize-handle {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  transition: background 0.2s;
  flex-shrink: 0;
}
.resize-handle:hover,
.resize-handle.active {
  background: var(--color-primary, #2563eb);
}

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
  position: relative;
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
  padding-right: 40px;
}
.tabs-scroll {
  display: flex;
  flex: 1;
  overflow: hidden;
  height: 100%;
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
.overflow-btn {
  flex-shrink: 0;
  margin: 0 4px;
  color: var(--color-text-1) !important;
  background: var(--color-fill-2);
  border-radius: 4px;
  padding: 0 8px !important;
  height: 26px;
  font-weight: 500;
}

/* Lock bar */
.lock-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: #FFF7E8;
  border-bottom: 1px solid #FFCF8B;
  font-size: 13px;
  color: #D25F00;
  flex-shrink: 0;
}

/* Toolbar */
.ide-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 48px 8px 14px;
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

/* ---- 右侧 Activity Bar ---- */
.right-bar {
  position: absolute;
  right: 0;
  top: 38px;
  bottom: 0;
  width: 36px;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 8px;
  gap: 4px;
  background: var(--color-bg-base);
  border-left: 1px solid var(--color-border);
  z-index: 11;
}
.rbar-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  cursor: pointer;
  color: var(--color-text-3);
  transition: all 0.15s;
}
.rbar-icon:hover { background: var(--color-fill-2); color: var(--color-text-1); }
.rbar-icon.active { background: var(--color-primary-light-1); color: var(--color-primary); }

.right-panel {
  position: absolute;
  right: 36px;
  top: 38px;
  bottom: 0;
  width: 300px;
  background: var(--color-bg-surface, #fff);
  border-left: 1px solid var(--color-border);
  z-index: 10;
  display: flex;
  flex-direction: column;
  box-shadow: -2px 0 8px rgba(0,0,0,0.06);
}
.rpanel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  font-weight: 500;
  font-size: 13px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.rpanel-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}
.rpanel-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}
.rpanel-field label {
  font-size: 11px;
  color: var(--color-text-3);
  font-weight: 500;
}
.rpanel-field span {
  font-size: 13px;
  color: var(--color-text-1);
}
.rpanel-empty {
  color: var(--color-text-3);
  font-size: 13px;
  text-align: center;
  padding: 40px 12px;
}
.rpanel-hint {
  font-size: 12px;
  color: var(--color-text-3);
  margin-bottom: 10px;
}
.param-row-mini {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
}

/* 右侧面板滑入动画 */
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(20px);
  opacity: 0;
}
</style>
