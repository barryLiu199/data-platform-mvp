<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { getExecutionStatus } from '../constants/status'
import { getDSInstances, getDSInstanceTasks, getDSTaskLog, rerunDSInstance } from '../api'

interface Instance {
  id: number; name: string; state: string
  startTime: string; endTime: string; duration: string
}
interface Task {
  id: number; name: string; state: string
  startTime: string; endTime: string; duration: string
}

const router = useRouter()
const instances = ref<Instance[]>([])
const loading = ref(false)
const statusFilter = ref('')
const dateRange = ref<string[]>([])
const taskMap = ref<Record<number, Task[]>>({})
const taskLoading = ref<Record<number, boolean>>({})
const expandedKeys = ref<number[]>([])
const logVisible = ref(false)
const logContent = ref('')
const logLoading = ref(false)
const autoRefresh = ref(false)
const lastUpdated = ref(0)
let timer: ReturnType<typeof setInterval> | null = null
let tickTimer: ReturnType<typeof setInterval> | null = null
let rerunTimer: ReturnType<typeof setTimeout> | null = null

const STATUS_TABS = [
  { label: '全部', value: '' },
  { label: '成功', value: 'SUCCESS' },
  { label: '失败', value: 'FAILURE' },
  { label: '运行中', value: 'RUNNING_EXECUTION' },
  { label: '停止', value: 'STOP' },
]

function stateInfo(state: string) {
  return getExecutionStatus(state)
}

// KPI 计算
const kpi = computed(() => {
  const all = instances.value
  const total = all.length
  const success = all.filter(i => i.state === 'SUCCESS').length
  const running = all.filter(i => i.state === 'RUNNING_EXECUTION').length
  const failed = all.filter(i => i.state === 'FAILURE').length
  const rate = total > 0 ? Math.round((success / total) * 100) : 0
  return { total, success, running, failed, rate }
})

const lastUpdatedText = computed(() => {
  const s = lastUpdated.value
  if (s < 5) return '刚刚更新'
  if (s < 60) return `${s}s 前更新`
  return `${Math.floor(s / 60)}m 前更新`
})

onMounted(() => {
  loadInstances()
  tickTimer = setInterval(() => { lastUpdated.value++ }, 1000)
})
onUnmounted(() => {
  stopAutoRefresh()
  if (tickTimer) clearInterval(tickTimer)
  if (rerunTimer) clearTimeout(rerunTimer)
})

async function loadInstances() {
  loading.value = true
  try {
    const params: Record<string, any> = { pageNo: 1, pageSize: 50 }
    if (statusFilter.value) params.stateType = statusFilter.value
    if (dateRange.value?.length === 2) {
      params.startDate = dateRange.value[0]
      params.endDate = dateRange.value[1]
    }
    const res: any = await getDSInstances(params)
    instances.value = (res.list || res.totalList || res.data?.list || []).map((item: any) => ({
      id: item.id,
      name: item.name || `工作流-${item.processDefinitionCode || item.id}`,
      state: item.state,
      startTime: item.startTime ? formatTime(item.startTime) : '-',
      endTime: item.endTime ? formatTime(item.endTime) : '-',
      duration: item.duration != null ? formatDuration(item.duration) : '-',
    }))
    lastUpdated.value = 0
  } catch (e: any) {
    Message.error('加载失败：' + (e?.response?.data?.detail || e?.message || '未知错误'))
  } finally { loading.value = false }
}

function setStatus(s: string) {
  statusFilter.value = s
  expandedKeys.value = []
  taskMap.value = {}
  loadInstances()
}

async function toggleExpand(id: number) {
  const idx = expandedKeys.value.indexOf(id)
  if (idx >= 0) { expandedKeys.value.splice(idx, 1); return }
  expandedKeys.value.push(id)
  if (taskMap.value[id]) return
  taskLoading.value[id] = true
  try {
    const res: any = await getDSInstanceTasks(id)
    const taskList = Array.isArray(res) ? res : (res.taskList || res.list || [])
    taskMap.value[id] = taskList.map((t: any) => ({
      id: t.id, name: t.name, state: t.state,
      startTime: t.startTime ? formatTime(t.startTime) : '-',
      endTime: t.endTime ? formatTime(t.endTime) : '-',
      duration: t.duration != null ? formatDuration(t.duration) : '-',
    }))
  } catch { taskMap.value[id] = [] }
  finally { taskLoading.value[id] = false }
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
    rerunTimer = setTimeout(loadInstances, 1000)
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

function formatTime(ts: string | number): string {
  if (!ts) return '-'
  const d = new Date(typeof ts === 'number' ? ts : ts)
  if (isNaN(d.getTime())) return String(ts)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatDuration(s: number): string {
  if (s == null || s < 0) return '-'
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m${s % 60}s`
  return `${Math.floor(m / 60)}h${m % 60}m`
}
</script>

<template>
  <div class="ops-page">
    <!-- KPI 卡片 -->
    <div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-value">{{ kpi.total }}</div>
        <div class="kpi-label">本次加载</div>
      </div>
      <div class="kpi-card kpi-card--success">
        <div class="kpi-value">{{ kpi.rate }}%</div>
        <div class="kpi-label">成功率</div>
      </div>
      <div class="kpi-card kpi-card--running">
        <div class="kpi-value">
          <span v-if="kpi.running > 0" class="pulse-dot"></span>
          {{ kpi.running }}
        </div>
        <div class="kpi-label">运行中</div>
      </div>
      <div class="kpi-card kpi-card--fail">
        <div class="kpi-value">{{ kpi.failed }}</div>
        <div class="kpi-label">异常</div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="status-tabs">
        <span v-for="tab in STATUS_TABS" :key="tab.value"
          class="status-tab" :class="{ active: statusFilter === tab.value }"
          @click="setStatus(tab.value)">{{ tab.label }}</span>
      </div>
      <div class="filter-right">
        <a-range-picker v-model="dateRange" style="width:240px" @change="loadInstances" />
        <span class="last-updated">{{ lastUpdatedText }}</span>
        <a-button size="mini" :type="autoRefresh ? 'primary' : 'outline'" @click="toggleAutoRefresh">
          {{ autoRefresh ? '● 实时' : '自动刷新' }}
        </a-button>
        <a-button size="mini" @click="loadInstances" :loading="loading">刷新</a-button>
      </div>
    </div>

    <!-- 实例列表 -->
    <div class="instance-list">
      <div v-if="loading && !instances.length" class="list-empty"><a-spin /></div>
      <div v-else-if="!instances.length" class="list-empty">
        <a-empty description="暂无运行实例" />
      </div>
      <div v-else>
        <div v-for="inst in instances" :key="inst.id" class="instance-card">
          <!-- 实例头部 -->
          <div class="inst-header" @click="toggleExpand(inst.id)">
            <span class="inst-expand" :class="{ expanded: expandedKeys.includes(inst.id) }">▶</span>
            <span class="inst-name" @click.stop="goDetail(inst.id)">{{ inst.name }}</span>
            <span class="inst-state-badge"
              :style="{ color: stateInfo(inst.state).color, background: stateInfo(inst.state).bg }">
              <span v-if="inst.state === 'RUNNING_EXECUTION'" class="pulse-dot-sm"></span>
              {{ stateInfo(inst.state).label }}
            </span>
            <span class="inst-time">{{ inst.startTime }}</span>
            <span class="inst-duration">{{ inst.duration }}</span>
            <a-button type="text" size="mini" @click.stop="rerun(inst.id)" class="inst-rerun">重跑</a-button>
          </div>

          <!-- 时间线子任务 -->
          <div v-if="expandedKeys.includes(inst.id)" class="timeline-wrap">
            <div v-if="taskLoading[inst.id]" class="timeline-loading">
              <a-spin :size="16" /> 加载中...
            </div>
            <div v-else-if="!taskMap[inst.id]?.length" class="timeline-empty">暂无子任务</div>
            <div v-else class="timeline">
              <div v-for="(task, idx) in taskMap[inst.id]" :key="task.id" class="tl-item">
                <div class="tl-line-wrap">
                  <div class="tl-dot" :style="{ background: stateInfo(task.state).color }"
                    :class="{ 'tl-dot--pulse': task.state === 'RUNNING_EXECUTION' }"></div>
                  <div v-if="idx < taskMap[inst.id].length - 1" class="tl-line"></div>
                </div>
                <div class="tl-content">
                  <span class="tl-name">{{ task.name }}</span>
                  <span class="tl-state" :style="{ color: stateInfo(task.state).color }">
                    {{ stateInfo(task.state).label }}
                  </span>
                  <span class="tl-duration">{{ task.duration }}</span>
                  <a-button type="text" size="mini" @click="viewLog(task.id)" class="tl-log-btn">日志</a-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 日志弹窗 -->
    <a-modal v-model:visible="logVisible" title="任务日志" :width="820" :footer="false">
      <a-spin :loading="logLoading" style="width:100%; min-height:200px">
        <pre class="log-pre">{{ logContent || '加载中...' }}</pre>
      </a-spin>
    </a-modal>
  </div>
</template>

<style scoped>
.ops-page { padding: var(--space-5); display: flex; flex-direction: column; gap: var(--space-4); height: calc(100vh - 60px); overflow: hidden; }

.kpi-row { display: flex; gap: var(--space-3); flex-shrink: 0; }
.kpi-card { flex: 1; background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-4) var(--space-5); display: flex; flex-direction: column; gap: var(--space-1); }
.kpi-card--success { border-left: 3px solid var(--color-success); }
.kpi-card--running { border-left: 3px solid var(--color-primary); }
.kpi-card--fail    { border-left: 3px solid var(--color-danger); }
.kpi-value { font-size: 28px; font-weight: 700; color: var(--color-text-primary); display: flex; align-items: center; gap: var(--space-2); }
.kpi-label { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }

.filter-bar { display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
.status-tabs { display: flex; gap: var(--space-1); }
.status-tab { padding: 5px 14px; font-size: var(--font-size-sm); cursor: pointer; border-radius: var(--radius-sm); color: var(--color-text-secondary); transition: all 0.15s; }
.status-tab:hover { background: var(--color-primary-light); color: var(--color-primary); }
.status-tab.active { background: var(--color-primary); color: var(--color-text-inverse); }
.filter-right { display: flex; align-items: center; gap: var(--space-2); }
.last-updated { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }

.instance-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: var(--space-2); }
.list-empty { display: flex; align-items: center; justify-content: center; height: 200px; }

.instance-card { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); overflow: hidden; }
.inst-header { display: flex; align-items: center; gap: var(--space-3); padding: var(--space-3) var(--space-4); cursor: pointer; transition: background 0.15s; }
.inst-header:hover { background: var(--color-bg-elevated); }
.inst-expand { font-size: 10px; color: var(--color-text-tertiary); transition: transform 0.2s; flex-shrink: 0; }
.inst-expand.expanded { transform: rotate(90deg); }
.inst-name { font-weight: 600; font-size: var(--font-size-base); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
.inst-name:hover { color: var(--color-primary); text-decoration: underline; }
.inst-state-badge { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border-radius: var(--radius-full); font-size: var(--font-size-xs); font-weight: 500; flex-shrink: 0; }
.inst-time { font-size: var(--font-size-xs); color: var(--color-text-tertiary); flex-shrink: 0; }
.inst-duration { font-size: var(--font-size-xs); color: var(--color-text-tertiary); min-width: 50px; flex-shrink: 0; }
.inst-rerun { flex-shrink: 0; }

.timeline-wrap { padding: var(--space-2) var(--space-4) var(--space-3) 44px; border-top: 1px solid var(--color-border-subtle); background: var(--color-bg-elevated); }
.timeline-loading { color: var(--color-text-tertiary); font-size: var(--font-size-sm); display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) 0; }
.timeline-empty { color: var(--color-text-tertiary); font-size: var(--font-size-sm); padding: var(--space-2) 0; }
.timeline { display: flex; flex-direction: column; }
.tl-item { display: flex; gap: var(--space-3); }
.tl-line-wrap { display: flex; flex-direction: column; align-items: center; width: 16px; flex-shrink: 0; }
.tl-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; }
.tl-dot--pulse { animation: pulse-ring 1.5s ease-out infinite; }
.tl-line { flex: 1; width: 2px; background: var(--color-border); min-height: 12px; margin: 2px 0; }
.tl-content { display: flex; align-items: center; gap: var(--space-3); padding: 2px 0 10px; flex: 1; }
.tl-name { font-size: var(--font-size-sm); font-weight: 500; flex: 1; }
.tl-state { font-size: var(--font-size-xs); font-weight: 500; flex-shrink: 0; }
.tl-duration { font-size: var(--font-size-xs); color: var(--color-text-tertiary); min-width: 40px; flex-shrink: 0; }
.tl-log-btn { flex-shrink: 0; }

.pulse-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-primary); flex-shrink: 0; animation: pulse-ring 1.5s ease-out infinite; }
.pulse-dot-sm { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; animation: pulse-ring 1.5s ease-out infinite; }
@keyframes pulse-ring {
  0%   { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.4); }
  70%  { box-shadow: 0 0 0 6px rgba(37, 99, 235, 0); }
  100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0); }
}

.log-pre { margin: 0; font-size: var(--font-size-xs); line-height: 1.7; white-space: pre-wrap; word-break: break-all; background: #1a1a2e; color: #e2e8f0; padding: var(--space-4); border-radius: var(--radius-md); max-height: 500px; overflow-y: auto; font-family: var(--font-family-mono); }
</style>
