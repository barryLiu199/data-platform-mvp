<template>
  <div class="page">
    <PageHeader title="运行实例" description="查看工作流调度历史与实时运行状态">
      <template #actions>
        <a-space>
          <span class="last-updated">{{ lastUpdatedText }}</span>
          <a-button size="small" :type="autoRefresh ? 'primary' : 'secondary'" @click="toggleAutoRefresh">
            <span v-if="autoRefresh" class="auto-dot"></span>
            {{ autoRefresh ? '实时刷新' : '自动刷新' }}
          </a-button>
          <a-button size="small" @click="loadInstances" :loading="loading">刷新</a-button>
        </a-space>
      </template>
    </PageHeader>

    <!-- KPI 卡片 -->
    <div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-icon kpi-icon--total"><icon-apps /></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ kpi.total }}</div>
          <div class="kpi-label">总实例数</div>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon kpi-icon--success"><icon-check-circle /></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ kpi.rate }}<span class="kpi-unit">%</span></div>
          <div class="kpi-label">成功率</div>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon kpi-icon--running"><icon-loading /></div>
        <div class="kpi-body">
          <div class="kpi-value">
            <span v-if="kpi.running > 0" class="pulse-dot"></span>
            {{ kpi.running }}
          </div>
          <div class="kpi-label">运行中</div>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon kpi-icon--fail"><icon-close-circle /></div>
        <div class="kpi-body">
          <div class="kpi-value">{{ kpi.failed }}</div>
          <div class="kpi-label">异常</div>
        </div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <FilterTabs v-model="statusFilter" :tabs="statusTabs" @update:model-value="setStatus" />

    <div class="filter-bar">
      <a-space>
        <a-select
          v-model="workflowFilter"
          placeholder="全部工作流"
          style="width: 180px;"
          allow-clear
          @change="loadInstances"
        >
          <a-option v-for="w in workflowList" :key="w.code" :value="w.code">{{ w.name }}</a-option>
        </a-select>
        <a-input-search
          v-model="keyword"
          placeholder="搜索实例名/ID"
          style="width: 200px;"
          allow-clear
          @search="loadInstances"
          @clear="loadInstances"
        />
        <a-range-picker v-model="dateRange" style="width:260px" @change="loadInstances" />
      </a-space>
    </div>

    <!-- 实例表格 -->
    <div class="glass-card table-card">
      <a-table
        :data="instances"
        :loading="loading"
        :bordered="false"
        :pagination="false"
        stripe
        :expandable="expandable"
        row-key="id"
        :scroll="{ x: 1300 }"
      >
        <template #columns>
          <a-table-column title="实例 ID" :width="80">
            <template #cell="{ record }">
              <span class="mono id-link" @click="goDetail(record.id)">{{ record.id }}</span>
            </template>
          </a-table-column>
          <a-table-column title="工作流名称" :width="200">
            <template #cell="{ record }">
              <span class="wf-name-link" @click="goDetail(record.id)">{{ record.name }}</span>
            </template>
          </a-table-column>
          <a-table-column title="触发" :width="120">
            <template #cell="{ record }">
              <div class="trigger-cell">
                <span class="trigger-tag" :class="'trigger--' + record.triggerType">
                  {{ triggerLabel(record.triggerType) }}
                </span>
                <span v-if="bizDateText(record)" class="biz-date mono">{{ bizDateText(record) }}</span>
              </div>
            </template>
          </a-table-column>
          <a-table-column title="状态" :width="100">
            <template #cell="{ record }">
              <span class="state-badge"
                :style="{ color: stateInfo(record.state).color, background: stateInfo(record.state).bg }">
                <span v-if="record.state === 'RUNNING'" class="pulse-dot-sm"></span>
                {{ stateInfo(record.state).label }}
              </span>
            </template>
          </a-table-column>
          <a-table-column title="开始时间" :width="160">
            <template #cell="{ record }">
              <a-tooltip :content="record.startTime || '-'">
                <span class="mono text-muted">{{ relativeDate(record.startTime) }}</span>
              </a-tooltip>
            </template>
          </a-table-column>
          <a-table-column title="结束时间" :width="160">
            <template #cell="{ record }">
              <a-tooltip :content="record.endTime || '-'">
                <span class="mono text-muted">{{ record.endTime ? relativeDate(record.endTime) : '-' }}</span>
              </a-tooltip>
            </template>
          </a-table-column>
          <a-table-column title="耗时" :width="80">
            <template #cell="{ record }">
              <span class="mono text-muted">{{ formatDuration(record.duration) }}</span>
            </template>
          </a-table-column>
          <a-table-column title="重试" :width="60">
            <template #cell="{ record }">
              <span class="mono text-muted">{{ record.runTimes ?? '-' }}</span>
            </template>
          </a-table-column>
          <a-table-column title="触发人" :width="100">
            <template #cell="{ record }">
              <span class="text-muted">{{ record.executorName || '-' }}</span>
            </template>
          </a-table-column>
          <a-table-column title="操作" :width="180" fixed="right">
            <template #cell="{ record }">
              <a-space :size="4">
                <a-button type="text" size="mini" @click="goDetail(record.id)">详情</a-button>
                <a-popconfirm content="确认重跑此实例？" @ok="rerun(record.id)">
                  <a-button type="text" size="mini" status="warning">重跑</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table-column>
        </template>
        <template #expand-row="{ record }">
          <div class="expand-tasks">
            <div v-if="taskLoading[record.id]" class="expand-loading">
              <a-spin :size="16" /> 加载中...
            </div>
            <div v-else-if="!taskMap[record.id]?.length" class="expand-empty">暂无子任务</div>
            <div v-else class="timeline">
              <div v-for="(task, idx) in taskMap[record.id]" :key="task.id" class="tl-item">
                <div class="tl-line-wrap">
                  <div class="tl-dot" :style="{ background: stateInfo(task.state).color }"
                    :class="{ 'tl-dot--pulse': task.state === 'RUNNING' }"></div>
                  <div v-if="idx < taskMap[record.id].length - 1" class="tl-line"></div>
                </div>
                <div class="tl-content">
                  <span class="tl-task-type">{{ task.taskType || 'TASK' }}</span>
                  <span class="tl-name">{{ task.name }}</span>
                  <span class="tl-state" :style="{ color: stateInfo(task.state).color }">
                    {{ stateInfo(task.state).label }}
                  </span>
                  <span class="tl-duration mono">{{ formatDuration(task.duration) }}</span>
                  <a-button type="text" size="mini" @click="viewLog(task.id)">日志</a-button>
                </div>
              </div>
            </div>
          </div>
        </template>
        <template #empty>
          <EmptyState description="暂无运行实例">
            <p class="text-muted">工作流运行后，实例记录将显示在这里</p>
          </EmptyState>
        </template>
      </a-table>
      <div class="pagination-wrap" v-if="total > pageSize">
        <a-pagination v-model:current="page" :total="total" :page-size="pageSize" show-total @change="loadInstances" />
      </div>
    </div>

    <!-- 日志弹窗 -->
    <a-modal v-model:visible="logVisible" title="任务日志" :width="860" :footer="false" unmount-on-close>
      <a-spin :loading="logLoading" style="width:100%; min-height:200px">
        <pre class="log-pre">{{ logContent || '加载中...' }}</pre>
      </a-spin>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { IconApps, IconCheckCircle, IconLoading, IconCloseCircle } from '@arco-design/web-vue/es/icon'
import PageHeader from '../components/PageHeader.vue'
import FilterTabs from '../components/FilterTabs.vue'
import EmptyState from '../components/EmptyState.vue'
import { getExecutionStatus } from '../constants/status'
import type { FilterTab } from '../components/FilterTabs.vue'
import { relativeDate, formatDuration } from '../utils/time'
import {
  getDSInstances, getDSInstanceTasks, getDSTaskLog, rerunDSInstance,
  getWorkflows,
} from '../api'

interface Instance {
  id: number; name: string; state: string; triggerType: string
  processDefinitionCode?: number
  startTime: string; endTime: string; duration: number | null
  runTimes?: number
  scheduleTime?: string; bizDate?: string; commandType?: string; executorName?: string
}
interface Task {
  id: number; name: string; state: string; taskType: string
  startTime: string; endTime: string; duration: number | null
}

const router = useRouter()
const instances = ref<Instance[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const statusFilter = ref('')
const dateRange = ref<string[]>([])
const keyword = ref('')
const workflowFilter = ref<number | undefined>(undefined)
const workflowList = ref<{ code: number; name: string }[]>([])
const taskMap = ref<Record<number, Task[]>>({})
const taskLoading = ref<Record<number, boolean>>({})
const logVisible = ref(false)
const logContent = ref('')
const logLoading = ref(false)
const autoRefresh = ref(false)
const lastUpdated = ref(0)
let timer: ReturnType<typeof setInterval> | null = null
let tickTimer: ReturnType<typeof setInterval> | null = null

const statusTabs = computed<FilterTab[]>(() => [
  { label: '全部', value: '', count: total.value },
  { label: '成功', value: 'SUCCESS' },
  { label: '失败', value: 'FAILURE' },
  { label: '运行中', value: 'RUNNING' },
  { label: '停止', value: 'STOP' },
])

function stateInfo(state: string) {
  return getExecutionStatus(state)
}

function triggerLabel(t: string) {
  return ({ manual: '手动', schedule: '调度', complement: '补数' } as any)[t] || t
}

// 业务日期：补数/调度优先显示业务日期，方便区分跑的是哪天
function bizDateText(record: Instance): string {
  const raw = record.bizDate || record.scheduleTime || ''
  if (!raw) return ''
  // 只取日期部分 "YYYY-MM-DD"
  const m = String(raw).match(/(\d{4}-\d{2}-\d{2})/)
  return m ? m[1] : ''
}

// KPI
const kpi = computed(() => {
  const all = instances.value
  const t = total.value || all.length
  const success = all.filter(i => i.state === 'SUCCESS').length
  const running = all.filter(i => i.state === 'RUNNING').length
  const failed = all.filter(i => i.state === 'FAILURE').length
  const rate = t > 0 ? Math.round((success / (t || 1)) * 100) : 0
  return { total: t, success, running, failed, rate }
})

const lastUpdatedText = computed(() => {
  const s = lastUpdated.value
  if (s < 5) return '刚刚更新'
  if (s < 60) return `${s}s 前`
  return `${Math.floor(s / 60)}m 前`
})

// 展开行
const expandable = reactive({
  expandedRowKeys: [] as number[],
  onExpand: (id: number) => {
    const keys = expandable.expandedRowKeys
    const idx = keys.indexOf(id)
    if (idx >= 0) { keys.splice(idx, 1); return }
    keys.push(id)
    if (!taskMap.value[id]) loadTasks(id)
  },
})

onMounted(async () => {
  tickTimer = setInterval(() => { lastUpdated.value++ }, 1000)
  // 加载工作流列表（用于下拉筛选）
  try {
    const res: any = await getWorkflows({ page: 1, page_size: 200 })
    workflowList.value = (res?.items || [])
      .filter((w: any) => w.ds_process_code)
      .map((w: any) => ({ code: w.ds_process_code, name: w.name }))
  } catch {}
  loadInstances()
})

onUnmounted(() => {
  stopAutoRefresh()
  if (tickTimer) clearInterval(tickTimer)
})

async function loadInstances() {
  loading.value = true
  try {
    const params: Record<string, any> = { pageNo: page.value, pageSize: pageSize.value }
    if (statusFilter.value) params.stateType = statusFilter.value
    if (dateRange.value?.length === 2) {
      params.startDate = dateRange.value[0]
      params.endDate = dateRange.value[1]
    }
    if (workflowFilter.value) params.processDefinitionCode = workflowFilter.value
    if (keyword.value) params.keyword = keyword.value
    const res: any = await getDSInstances(params)
    instances.value = (res.list || []).map((item: any) => ({
      id: item.id,
      name: item.name,
      state: item.state,
      triggerType: item.triggerType || 'manual',
      processDefinitionCode: item.processDefinitionCode,
      startTime: item.startTime,
      endTime: item.endTime,
      duration: item.duration,
      runTimes: item.runTimes,
      scheduleTime: item.scheduleTime,
      bizDate: item.bizDate,
      commandType: item.commandType,
      executorName: item.executorName,
    }))
    total.value = res.total || 0
    lastUpdated.value = 0
  } catch (e: any) {
    Message.error('加载失败：' + (e?.response?.data?.detail || e?.message || '未知错误'))
  } finally { loading.value = false }
}

async function loadTasks(instanceId: number) {
  taskLoading.value[instanceId] = true
  try {
    const res: any = await getDSInstanceTasks(instanceId)
    const taskList = Array.isArray(res) ? res : (res.taskList || res.list || [])
    taskMap.value[instanceId] = taskList.map((t: any) => ({
      id: t.id, name: t.name, state: t.state, taskType: t.taskType || '',
      startTime: t.startTime, endTime: t.endTime, duration: t.duration,
    }))
  } catch { taskMap.value[instanceId] = [] }
  finally { taskLoading.value[instanceId] = false }
}

function setStatus(s: string) {
  statusFilter.value = s
  page.value = 1
  loadInstances()
}

async function viewLog(taskId: number) {
  logLoading.value = true; logVisible.value = true; logContent.value = ''
  try {
    const res: any = await getDSTaskLog(taskId)
    logContent.value = res.log || res.message || res.data || '暂无日志'
  } catch { logContent.value = '获取日志失败' }
  finally { logLoading.value = false }
}

async function rerun(instanceId: number) {
  try {
    await rerunDSInstance(instanceId)
    Message.success('已触发重跑')
    setTimeout(loadInstances, 1000)
  } catch (e: any) { Message.error(e?.response?.data?.detail || '重跑失败') }
}

function goDetail(id: number) {
  router.push(`/ops/instances/${id}`)
}

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) {
    timer = setInterval(loadInstances, 30000)
  } else { stopAutoRefresh() }
}

function stopAutoRefresh() {
  if (timer) { clearInterval(timer); timer = null }
  autoRefresh.value = false
}
</script>

<style scoped>
.page { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

/* KPI 卡片 */
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-4); margin-bottom: var(--space-4); }
.kpi-card {
  display: flex; align-items: center; gap: var(--space-4);
  background: var(--color-bg-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius-lg); padding: var(--space-4) var(--space-5);
  transition: box-shadow 0.15s;
}
.kpi-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.kpi-icon {
  width: 40px; height: 40px; border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0;
}
.kpi-icon--total   { background: var(--color-primary-light); color: var(--color-primary); }
.kpi-icon--success { background: #F0FDF4; color: #16A34A; }
.kpi-icon--running { background: #EFF6FF; color: #2563EB; }
.kpi-icon--fail    { background: #FEF2F2; color: #DC2626; }
.kpi-body { display: flex; flex-direction: column; gap: 2px; }
.kpi-value { font-size: 24px; font-weight: 700; color: var(--color-text-primary); display: flex; align-items: center; gap: 6px; line-height: 1.2; }
.kpi-unit { font-size: 14px; font-weight: 500; color: var(--color-text-tertiary); }
.kpi-label { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }

/* 筛选 */
.filter-bar { display: flex; align-items: center; margin-bottom: var(--space-4); }
.last-updated { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.auto-dot { width: 6px; height: 6px; border-radius: 50%; background: #fff; display: inline-block; margin-right: 4px; animation: blink 1.5s infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

/* 表格 */
.table-card { padding: 0; overflow: auto; }
.id-link { cursor: pointer; color: var(--color-primary); }
.id-link:hover { text-decoration: underline; }
.wf-name-link { font-weight: 500; color: var(--color-primary); cursor: pointer; }
.wf-name-link:hover { text-decoration: underline; }
.mono { font-family: var(--font-family-mono); font-size: var(--font-size-xs); }
.text-muted { color: var(--color-text-tertiary); }

/* 触发类型标签 */
.trigger-cell { display: inline-flex; align-items: center; gap: 6px; }
.biz-date { color: var(--color-text-tertiary); font-size: 11px; }
.trigger-tag {
  display: inline-block; padding: 1px 8px; border-radius: var(--radius-full);
  font-size: 11px; font-weight: 500;
}
.trigger--manual     { background: var(--color-bg-elevated); color: var(--color-text-secondary); }
.trigger--schedule   { background: #EFF6FF; color: #2563EB; }
.trigger--complement { background: #F5F3FF; color: #8B5CF6; }

/* 状态标签 */
.state-badge {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 10px; border-radius: var(--radius-full);
  font-size: var(--font-size-xs); font-weight: 500;
}

.pulse-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-primary); flex-shrink: 0; animation: pulse-ring 1.5s ease-out infinite; }
.pulse-dot-sm { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; animation: pulse-ring 1.5s ease-out infinite; }
@keyframes pulse-ring {
  0%   { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.4); }
  70%  { box-shadow: 0 0 0 6px rgba(37, 99, 235, 0); }
  100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0); }
}

/* 展开行 — 任务时间线 */
.expand-tasks { padding: var(--space-3) var(--space-4) var(--space-3) var(--space-6); }
.expand-loading { color: var(--color-text-tertiary); font-size: var(--font-size-sm); display: flex; align-items: center; gap: var(--space-2); }
.expand-empty { color: var(--color-text-tertiary); font-size: var(--font-size-sm); }
.timeline { display: flex; flex-direction: column; }
.tl-item { display: flex; gap: var(--space-3); }
.tl-line-wrap { display: flex; flex-direction: column; align-items: center; width: 16px; flex-shrink: 0; }
.tl-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; margin-top: 5px; }
.tl-dot--pulse { animation: pulse-ring 1.5s ease-out infinite; }
.tl-line { flex: 1; width: 2px; background: var(--color-border); min-height: 12px; margin: 2px 0; }
.tl-content { display: flex; align-items: center; gap: var(--space-3); padding: 3px 0 12px; flex: 1; }
.tl-task-type { font-size: 10px; font-family: var(--font-family-mono); background: var(--color-bg-elevated); color: var(--color-text-tertiary); padding: 1px 6px; border-radius: 3px; flex-shrink: 0; }
.tl-name { font-size: var(--font-size-sm); font-weight: 500; flex: 1; }
.tl-state { font-size: var(--font-size-xs); font-weight: 500; flex-shrink: 0; }
.tl-duration { color: var(--color-text-tertiary); flex-shrink: 0; }

.pagination-wrap { padding: var(--space-4) var(--space-6); display: flex; justify-content: flex-end; border-top: 1px solid var(--color-border-subtle); }

.log-pre {
  margin: 0; font-size: var(--font-size-xs); line-height: 1.7;
  white-space: pre-wrap; word-break: break-all;
  background: #1a1a2e; color: #e2e8f0;
  padding: var(--space-4); border-radius: var(--radius-md);
  max-height: 500px; overflow-y: auto; font-family: var(--font-family-mono);
}
</style>
