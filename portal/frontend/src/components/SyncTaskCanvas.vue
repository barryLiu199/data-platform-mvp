<template>
  <div class="task-canvas" v-if="ready">
    <!-- 锁定提示 -->
    <div v-if="locked && !isLockedByMe" class="lock-bar">
      <icon-lock style="font-size: 14px;" />
      <span>该任务正在被其他用户编辑，当前为只读模式</span>
    </div>
    <!-- 顶栏 -->
    <div class="canvas-header">
      <div class="title-area">
        <a-input
          v-model="form.name"
          placeholder="同步任务名称"
          class="task-title-input"
          size="large"
          :disabled="isOnline || (locked && !isLockedByMe)"
        />
      </div>
      <div class="action-area">
        <a-button
          v-if="props.taskId"
          type="primary"
          @click="handleRun"
          :loading="running"
          :disabled="locked && !isLockedByMe"
        >
          <template #icon><icon-play-arrow /></template>
          运行
        </a-button>
        <a-button @click="loadPreview" :loading="previewing">
          <template #icon><icon-eye /></template>
          预览 DataX
        </a-button>
        <a-button
          v-if="!isOnline"
          type="primary"
          @click="handleSave"
          :loading="saving"
          :disabled="locked && !isLockedByMe"
        >
          <template #icon><icon-save /></template>
          保存
        </a-button>
        <a-button
          v-if="props.taskId && !isOnline"
          status="success"
          @click="handleOnline"
          :loading="toggling"
          :disabled="locked && !isLockedByMe"
        >
          <template #icon><icon-unlock /></template>
          上线
        </a-button>
        <a-button
          v-if="props.taskId && isOnline"
          @click="handleOffline"
          :loading="toggling"
          :disabled="locked && !isLockedByMe"
        >
          <template #icon><icon-lock /></template>
          下线
        </a-button>
      </div>
    </div>

    <div class="canvas-body">
      <!-- 基础信息 -->
      <section class="card-section">
        <div class="section-title">基础信息</div>
        <div class="form-row">
          <div class="form-item">
            <label>所属项目</label>
            <a-select v-model="form.project_id" placeholder="选择项目" :disabled="isOnline">
              <a-option v-for="p in projects" :key="p.id" :value="p.id">
                {{ p.name }}
              </a-option>
            </a-select>
          </div>
          <div class="form-item">
            <label>通道数</label>
            <a-input-number v-model="form.channel" :min="1" :max="32" placeholder="3" :disabled="isOnline" />
          </div>
        </div>
      </section>

      <!-- 来源配置 -->
      <section class="card-section">
        <div class="section-title">
          <icon-import /> 数据来源
        </div>
        <div class="form-row">
          <div class="form-item">
            <label>来源数据源 <span class="required">*</span></label>
            <a-select
              v-model="form.source_id"
              placeholder="选择来源数据源"
              show-search
              :filter-option="dsFilter"
              @change="onSourceDsChange"
              :disabled="isOnline"
            >
              <a-option v-for="d in datasources" :key="d.id" :value="d.id">
                {{ d.name }} ({{ d.type }})
              </a-option>
            </a-select>
          </div>
          <div class="form-item">
            <label>来源表 <span class="required">*</span></label>
            <a-auto-complete
              v-model="form.source_table"
              placeholder="输入关键字搜索（如 user, brand）"
              :data="sourceTableOptions"
              :trigger-props="{ autoFitPopupMinWidth: true }"
              @search="onSearchSourceTable"
              @change="onSourceTableChange"
              allow-clear
              :disabled="isOnline"
            />
          </div>
        </div>
        <div class="form-row">
          <div class="form-item span-2">
            <label>数据过滤 WHERE（可选，支持 ${'$'}{bizdate} 等变量）</label>
            <a-input
              v-model="form.where_clause"
              placeholder="如：dt = '${bizdate}' AND status = 1"
              :disabled="isOnline"
            />
          </div>
          <div class="form-item">
            <label>切分键 splitPk（默认取第一列）</label>
            <a-select v-model="form.split_pk" placeholder="可选" allow-clear :disabled="isOnline">
              <a-option v-for="c in sourceColumns" :key="c.name" :value="c.name">
                {{ c.name }} ({{ c.type }})
              </a-option>
            </a-select>
          </div>
        </div>
      </section>

      <!-- 去向配置 -->
      <section class="card-section">
        <div class="section-title">
          <icon-export /> 数据去向
        </div>
        <div class="form-row">
          <div class="form-item">
            <label>去向数据源 <span class="required">*</span></label>
            <a-select
              v-model="form.target_id"
              placeholder="选择去向数据源"
              show-search
              :filter-option="dsFilter"
              @change="onTargetDsChange"
              :disabled="isOnline"
            >
              <a-option v-for="d in datasources" :key="d.id" :value="d.id">
                {{ d.name }} ({{ d.type }})
              </a-option>
            </a-select>
          </div>
          <div class="form-item">
            <label>目标表 <span class="required">*</span></label>
            <a-auto-complete
              v-model="form.target_table"
              placeholder="选择或输入表名（不存在可一键建表）"
              :data="targetTableOptions"
              @search="onSearchTargetTable"
              @change="onTargetTableChange"
              allow-clear
              :disabled="isOnline"
            />
          </div>
          <div class="form-item">
            <label>写入模式</label>
            <a-select v-model="form.write_mode" :disabled="isOnline">
              <a-option value="insert">insert</a-option>
              <a-option value="replace">replace</a-option>
              <a-option value="update">update</a-option>
            </a-select>
          </div>
        </div>
        <div class="form-row">
          <div class="form-item span-2">
            <label>导入前准备语句 preSql（目标库执行，每行一条）</label>
            <a-textarea
              v-model="preSqlText"
              placeholder="如：TRUNCATE TABLE ${targetTable}"
              :auto-size="{ minRows: 2, maxRows: 6 }"
              :disabled="isOnline"
            />
          </div>
          <div class="form-item span-2">
            <label>导入后准备语句 postSql（目标库执行，每行一条）</label>
            <a-textarea
              v-model="postSqlText"
              placeholder="如：ANALYZE TABLE ${targetTable}"
              :auto-size="{ minRows: 2, maxRows: 6 }"
              :disabled="isOnline"
            />
          </div>
        </div>
      </section>

      <!-- 同步配置 -->
      <section class="card-section">
        <div class="section-title">
          <icon-sync /> 同步配置
        </div>
        <div class="form-row">
          <div class="form-item">
            <label>同步方式</label>
            <a-radio-group v-model="form.sync_type" type="button" :disabled="isOnline">
              <a-radio value="full">全量</a-radio>
              <a-radio value="increment">增量</a-radio>
            </a-radio-group>
          </div>
          <div v-if="form.sync_type === 'increment'" class="form-item">
            <label>增量字段</label>
            <a-select v-model="form.increment_column" placeholder="选择增量字段" :disabled="isOnline">
              <a-option v-for="c in sourceColumns" :key="c.name" :value="c.name">
                {{ c.name }} ({{ c.type }})
              </a-option>
            </a-select>
          </div>
        </div>
      </section>

      <!-- 字段映射（放最底部） -->
      <section class="card-section mapping-section">
        <div class="section-title">
          <icon-swap /> 字段映射
          <span v-if="!sourceColumns.length || !targetColumns.length" class="title-hint">
            （请先在上面选择来源表 / 目标表）
          </span>
        </div>
        <FieldMappingCanvas
          v-model="form.field_mapping"
          :source-columns="sourceColumns"
          :target-columns="targetColumns"
          :enable-auto-create="!!form.target_id && !!form.target_table"
          :readonly="isOnline"
          @auto-create-table="handleAutoCreateTable"
        />
      </section>
    </div>

    <!-- 一键建表 预览弹窗 -->
    <a-modal
      v-model:visible="ddlModalVisible"
      title="一键建表 — DDL 预览"
      @ok="confirmExecuteDDL"
      :ok-loading="ddlExecuting"
      :ok-text="'执行建表'"
      width="640px"
    >
      <a-textarea v-model="ddlText" :auto-size="{ minRows: 8, maxRows: 16 }" style="font-family: 'SF Mono', Menlo, Consolas, monospace;" />
      <div class="hint-text">该 DDL 将在<b>目标数据源</b>执行；如表已存在会被跳过 (CREATE TABLE IF NOT EXISTS)</div>
    </a-modal>

    <!-- 预览 DataX 弹窗 -->
    <a-modal
      v-model:visible="previewModalVisible"
      title="DataX 配置预览（密码已打码）"
      width="800px"
      :footer="false"
    >
      <pre class="preview-pre">{{ previewJson }}</pre>
    </a-modal>

  </div>
  <div v-else class="empty-state">
    <icon-folder class="empty-icon" />
    <p>请在左侧选择或新建一个同步任务</p>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, nextTick } from 'vue'
import { Message } from '@arco-design/web-vue'
import {
  IconImport, IconExport, IconSync, IconSwap, IconEye, IconCode,
  IconSave, IconFolder, IconLock, IconUnlock, IconPlayArrow,
} from '@arco-design/web-vue/es/icon'
import {
  getSyncTask, createSyncTask, updateSyncTask, previewSyncTaskUnsaved,
  getDatasources, getMetadataTables, getMetadataColumns,
  generateDDL, executeDDL, setSyncTaskStatus, createComponent,
  runSyncTask,
} from '../api'
import FieldMappingCanvas from './FieldMappingCanvas.vue'

const props = defineProps<{
  taskId: number | null  // null = 新建态
  projectId?: number | null
  projects: any[]
  locked?: boolean
  lockedByMe?: boolean
}>()

const emit = defineEmits<{ 'saved': [task: any]; 'open-script': []; 'status-changed': [task: any] }>()

const ready = ref(true)
const task = ref<any>(null)
const datasources = ref<any[]>([])

const form = reactive<any>({
  name: '',
  project_id: null,
  source_id: null,
  target_id: null,
  source_table: '',
  target_table: '',
  sync_type: 'full',
  increment_column: null,
  field_mapping: [] as any[],
  where_clause: '',
  split_pk: null,
  write_mode: 'insert',
  channel: 3,
})

const preSqlText = ref('')
const postSqlText = ref('')

const sourceColumns = ref<any[]>([])
const targetColumns = ref<any[]>([])

const sourceTableOptions = ref<string[]>([])
const targetTableOptions = ref<string[]>([])

const isOnline = computed(() => task.value?.status === 'active')
const locked = computed(() => props.locked ?? false)
const isLockedByMe = computed(() => props.lockedByMe ?? true)
const toggling = ref(false)
const running = ref(false)

const saving = ref(false)
const previewing = ref(false)
const previewModalVisible = ref(false)
const previewJson = ref('')

const ddlModalVisible = ref(false)
const ddlText = ref('')
const ddlExecuting = ref(false)



const dsFilter = (input: string, opt: any) => {
  const txt = (opt.children?.[0]?.children || '') as string
  return txt.toLowerCase().includes(input.toLowerCase())
}

// ---- 加载 ----
async function loadDatasources() {
  try {
    const res: any = await getDatasources({ page: 1, page_size: 100 })
    datasources.value = (res.items || []).filter((d: any) => d.host && d.username)
  } catch {}
}

async function loadTask() {
  if (!props.taskId) {
    // 新建态：重置
    Object.assign(form, {
      name: '',
      project_id: props.projectId ?? null,
      source_id: null,
      target_id: null,
      source_table: '',
      target_table: '',
      sync_type: 'full',
      increment_column: null,
      field_mapping: [],
      where_clause: '',
      split_pk: null,
      write_mode: 'insert',
      channel: 3,
    })
    preSqlText.value = ''
    postSqlText.value = ''
    sourceColumns.value = []
    targetColumns.value = []
    task.value = null
    return
  }
  try {
    const res: any = await getSyncTask(props.taskId)
    task.value = res
    Object.assign(form, {
      name: res.name,
      project_id: res.project_id,
      source_id: res.source_id,
      target_id: res.target_id,
      source_table: res.source_table,
      target_table: res.target_table,
      sync_type: res.sync_type || 'full',
      increment_column: res.increment_column,
      field_mapping: res.field_mapping || [],
      where_clause: res.where_clause || '',
      split_pk: res.split_pk,
      write_mode: res.write_mode || 'insert',
      channel: res.channel ?? 3,
    })
    preSqlText.value = (res.pre_sql || []).join('\n')
    postSqlText.value = (res.post_sql || []).join('\n')
    if (form.source_id && form.source_table) await loadSourceColumns()
    if (form.target_id && form.target_table) await loadTargetColumns()
  } catch {}
}

async function onSourceDsChange() {
  form.source_table = ''
  sourceColumns.value = []
  await onSearchSourceTable('')
}

async function onTargetDsChange() {
  form.target_table = ''
  targetColumns.value = []
  await onSearchTargetTable('')
}

let srcSearchTimer: number | null = null
async function onSearchSourceTable(kw: string) {
  if (!form.source_id) return
  if (srcSearchTimer) clearTimeout(srcSearchTimer)
  srcSearchTimer = window.setTimeout(async () => {
    try {
      const res: any = await getMetadataTables(form.source_id, kw || undefined, 50)
      sourceTableOptions.value = (res.tables || []).map((t: any) => t.name)
    } catch {}
  }, 200)
}

let dstSearchTimer: number | null = null
async function onSearchTargetTable(kw: string) {
  if (!form.target_id) return
  if (dstSearchTimer) clearTimeout(dstSearchTimer)
  dstSearchTimer = window.setTimeout(async () => {
    try {
      const res: any = await getMetadataTables(form.target_id, kw || undefined, 50)
      targetTableOptions.value = (res.tables || []).map((t: any) => t.name)
    } catch {}
  }, 200)
}

async function onSourceTableChange(v: string) {
  if (!form.source_id || !v) { sourceColumns.value = []; return }
  await loadSourceColumns()
}

async function onTargetTableChange(v: string) {
  if (!form.target_id || !v) { targetColumns.value = []; return }
  await loadTargetColumns()
}

async function loadSourceColumns() {
  if (!form.source_id || !form.source_table) return
  try {
    const res: any = await getMetadataColumns(form.source_id, form.source_table)
    sourceColumns.value = res.columns || []
  } catch { sourceColumns.value = [] }
}

async function loadTargetColumns() {
  if (!form.target_id || !form.target_table) return
  try {
    const res: any = await getMetadataColumns(form.target_id, form.target_table)
    targetColumns.value = res.columns || []
  } catch { targetColumns.value = [] }
}

// ---- 保存 ----
function buildPayload() {
  const preSql = preSqlText.value.split('\n').map(s => s.trim()).filter(Boolean)
  const postSql = postSqlText.value.split('\n').map(s => s.trim()).filter(Boolean)
  return {
    name: form.name,
    project_id: form.project_id,
    source_id: form.source_id,
    target_id: form.target_id,
    source_table: form.source_table,
    target_table: form.target_table,
    sync_type: form.sync_type,
    increment_column: form.increment_column,
    field_mapping: form.field_mapping,
    where_clause: form.where_clause || null,
    split_pk: form.split_pk || null,
    write_mode: form.write_mode || 'insert',
    channel: form.channel || 3,
    pre_sql: preSql.length ? preSql : null,
    post_sql: postSql.length ? postSql : null,
  }
}

async function handleSave() {
  if (!form.name) { Message.warning('请输入任务名称'); return }
  if (!form.source_id || !form.target_id) { Message.warning('请选择来源和去向数据源'); return }
  if (!form.source_table || !form.target_table) { Message.warning('请选择来源表和目标表'); return }
  if (!form.field_mapping || form.field_mapping.length === 0) {
    Message.warning('请至少配置一条字段映射'); return
  }
  saving.value = true
  try {
    const payload = buildPayload()
    let res: any
    if (props.taskId) {
      res = await updateSyncTask(props.taskId, payload)
      Message.success('任务已更新')
    } else {
      res = await createSyncTask(payload)
      // 自动创建关联的 Component，让左侧文件树出现节点
      try {
        const comp: any = await createComponent({
          name: form.name,
          type: 'datax',
          folder_id: null,
          config_json: {
            sync_task_id: res.id,
            source_table: form.source_table,
            target_table: form.target_table,
          },
        })
        res._component = comp
      } catch {}
      Message.success('同步任务已创建')
    }
    emit('saved', res)
  } catch (e: any) {
    // 错误消息已由拦截器展示
  } finally {
    saving.value = false
  }
}

async function handleOnline() {
  if (!props.taskId) { Message.warning('请先保存任务'); return }
  toggling.value = true
  try {
    const res: any = await setSyncTaskStatus(props.taskId, 'active')
    task.value = res
    Message.success('任务已上线，进入只读保护')
    emit('status-changed', res)
  } catch {} finally { toggling.value = false }
}

async function handleOffline() {
  if (!props.taskId) return
  toggling.value = true
  try {
    const res: any = await setSyncTaskStatus(props.taskId, 'draft')
    task.value = res
    Message.success('任务已下线，可以编辑')
    emit('status-changed', res)
  } catch {} finally { toggling.value = false }
}

async function handleRun() {
  if (!props.taskId) { Message.warning('请先保存任务'); return }
  running.value = true
  try {
    const res: any = await runSyncTask(props.taskId)
    if (res.success) {
      Message.success(`运行成功 · ${res.duration_ms}ms`)
    } else {
      Message.error('运行失败，请查看日志')
    }
    if (res.stdout || res.stderr) {
      console.log('[DataX stdout]', res.stdout)
      if (res.stderr) console.warn('[DataX stderr]', res.stderr)
    }
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '运行失败')
  } finally { running.value = false }
}

async function loadPreview() {
  if (!form.source_id || !form.target_id || !form.source_table || !form.target_table) {
    Message.warning('请先填写来源/目标信息')
    return
  }
  if (!form.field_mapping?.length) { Message.warning('请先配置字段映射'); return }
  previewing.value = true
  try {
    const payload = buildPayload()
    const res: any = await previewSyncTaskUnsaved({
      source_id: payload.source_id,
      target_id: payload.target_id,
      source_table: payload.source_table,
      target_table: payload.target_table,
      sync_type: payload.sync_type,
      increment_column: payload.increment_column,
      field_mapping: payload.field_mapping,
      where_clause: payload.where_clause,
      split_pk: payload.split_pk,
      write_mode: payload.write_mode,
      pre_sql: payload.pre_sql,
      post_sql: payload.post_sql,
    })
    previewJson.value = JSON.stringify(res.datax, null, 2)
    previewModalVisible.value = true
  } catch {} finally {
    previewing.value = false
  }
}

// ---- 一键建表 ----
async function handleAutoCreateTable() {
  if (!form.target_id || !form.target_table) {
    Message.warning('请先选择目标数据源和目标表名')
    return
  }
  if (!sourceColumns.value.length) {
    Message.warning('未获取到源表字段，无法推断建表 SQL')
    return
  }
  try {
    const res: any = await generateDDL({
      datasource_id: form.target_id,
      target_table: form.target_table,
      columns: sourceColumns.value.map((c: any) => ({
        name: c.name,
        type: c.type,
        nullable: c.nullable,
        primary_key: c.primary_key,
        comment: c.comment,
      })),
    })
    ddlText.value = res.ddl || ''
    ddlModalVisible.value = true
  } catch {}
}

async function confirmExecuteDDL() {
  if (!ddlText.value.trim()) return
  ddlExecuting.value = true
  try {
    const res: any = await executeDDL({
      datasource_id: form.target_id,
      ddl: ddlText.value,
    })
    if (res.ok) {
      Message.success(res.message || '建表成功')
      ddlModalVisible.value = false
      await loadTargetColumns()
    } else {
      Message.error(res.message || '建表失败')
    }
  } catch {} finally {
    ddlExecuting.value = false
  }
}

watch(() => props.taskId, () => loadTask())

onMounted(async () => {
  await loadDatasources()
  await loadTask()
})
</script>

<style scoped>
.task-canvas {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #F7F8FA;
}

.canvas-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #E5E6EB;
}

.title-area {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}
.task-title-input {
  width: 280px;
  flex-shrink: 0;
}
.task-title-input :deep(.arco-input) {
  font-weight: 600;
  font-size: 15px;
}

.lock-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  background: #FFF7E8;
  border-bottom: 1px solid #FFCF8B;
  font-size: 13px;
  color: #D25F00;
}

.action-area {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
  flex-wrap: nowrap;
}

.canvas-body {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.card-section {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #1D2129;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.title-hint { font-size: 12px; font-weight: normal; color: #C9CDD4; margin-left: 4px; }

.form-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px 16px;
  margin-bottom: 8px;
}
.form-row:last-child { margin-bottom: 0; }
.form-item { display: flex; flex-direction: column; gap: 4px; }
.form-item label {
  font-size: 12px;
  color: #4E5969;
  line-height: 1.4;
}
.form-item .required { color: #F53F3F; }
.form-item.span-2 { grid-column: span 2; }

.mapping-section { padding-bottom: 20px; }

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #C9CDD4;
}
.empty-icon { font-size: 48px; margin-bottom: 12px; }

.preview-pre {
  margin: 0;
  padding: 12px;
  background: #1D2129;
  color: #E5E6EB;
  border-radius: 6px;
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  max-height: 60vh;
  overflow: auto;
  white-space: pre;
}
.hint-text { color: #86909C; font-size: 12px; margin-top: 6px; }

.run-result { display: flex; flex-direction: column; gap: 12px; }
.run-summary { margin-bottom: 4px; }
.run-section-title { font-size: 13px; font-weight: 600; color: #1D2129; margin-top: 4px; }
</style>
