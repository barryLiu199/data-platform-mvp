<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { getExecutionStatus } from '../constants/status'
import { getDSInstances, getDSInstanceTasks, getDSTaskLog, rerunDSInstance } from '../api'
import { relativeDate, formatDuration } from '../utils/time'

interface Task {
  id: number; name: string; state: string; taskType: string
  startTime: string; endTime: string; duration: number | null
}

const route = useRoute()
const router = useRouter()
const instanceId = Number(route.params.id)

const instanceInfo = ref<any>(null)
const tasks = ref<Task[]>([])
const loading = ref(false)
const rerunLoading = ref(false)
const logVisible = ref(false)
const logContent = ref('')
const logLoading = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | null = null

function stateInfo(state: string) {
  return getExecutionStatus(state)
}

function triggerLabel(t: string) {
  return ({ manual: '手动', schedule: '调度', complement: '补数' } as any)[t] || '手动'
}

const hasRunning = computed(() => tasks.value.some(t => t.state === 'RUNNING'))
const instanceState = computed(() => instanceInfo.value?.state || '')

onMounted(async () => {
  await loadInstance()
  await loadTasks()
  // 自动刷新：有运行中任务时每 3s 刷
  refreshTimer = setInterval(async () => {
    if (hasRunning.value || instanceState.value === 'RUNNING') {
      await loadTasks()
      await loadInstance()
    }
  }, 3000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

async function loadInstance() {
  try {
    const res: any = await getDSInstances({ pageNo: 1, pageSize: 1 })
    // 从列表中找到当前实例（DS 不提供单实例 API，用列表查）
    // 实际上 DS 的 process-instances 接口可以通过 id 过滤，但我们的代理没暴露
    // 用 tasks 列表的来源实例信息补充
    const list = res?.list || []
    const found = list.find((i: any) => i.id === instanceId)
    if (found) instanceInfo.value = found
  } catch {}
}

async function loadTasks() {
  loading.value = true
  try {
    const res: any = await getDSInstanceTasks(instanceId)
    const list = Array.isArray(res) ? res : (res.taskList || res.list || [])
    tasks.value = list.map((t: any) => ({
      id: t.id,
      name: t.name,
      state: t.state,
      taskType: t.taskType || '',
      startTime: t.startTime,
      endTime: t.endTime,
      duration: t.duration,
    }))
  } catch {
    Message.error('加载任务失败')
  } finally { loading.value = false }
}

async function viewLog(taskId: number) {
  logLoading.value = true; logVisible.value = true; logContent.value = ''
  try {
    const res: any = await getDSTaskLog(taskId)
    logContent.value = res.log || res.message || res.data || '暂无日志'
  } catch { logContent.value = '获取日志失败' }
  finally { logLoading.value = false }
}

async function handleRerun() {
  rerunLoading.value = true
  try {
    await rerunDSInstance(instanceId)
    Message.success('已触发重跑')
    setTimeout(async () => {
      await loadTasks()
      await loadInstance()
    }, 1500)
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '重跑失败')
  } finally { rerunLoading.value = false }
}

function handleBack() {
  // 优先回到实例列表，而不是 router.back() 可能回到外部
  router.push('/scheduler/history')
}
</script>

<template>
  <div class="detail-page">
    <!-- 顶部导航 + 实例信息 -->
    <div class="detail-header-card glass-card">
      <div class="header-top">
        <a-button type="text" size="small" @click="handleBack">
          <template #icon><icon-left /></template>
          返回列表
        </a-button>
        <div class="header-actions">
          <a-popconfirm content="确认重跑此实例？" @ok="handleRerun">
            <a-button type="primary" size="small" :loading="rerunLoading">重跑</a-button>
          </a-popconfirm>
        </div>
      </div>
      <div class="header-info">
        <div class="header-title-row">
          <span class="instance-title">{{ instanceInfo?.name || `实例 #${instanceId}` }}</span>
          <span class="instance-id mono">#{{ instanceId }}</span>
          <span v-if="instanceState" class="state-badge-lg"
            :style="{ color: stateInfo(instanceState).color, background: stateInfo(instanceState).bg }">
            <span v-if="instanceState === 'RUNNING'" class="pulse-dot-sm"></span>
            {{ stateInfo(instanceState).label }}
          </span>
        </div>
        <div class="header-meta">
          <div class="meta-item" v-if="instanceInfo?.triggerType">
            <span class="meta-label">触发类型</span>
            <span class="trigger-tag" :class="'trigger--' + instanceInfo.triggerType">
              {{ triggerLabel(instanceInfo.triggerType) }}
            </span>
          </div>
          <div class="meta-item" v-if="instanceInfo?.startTime">
            <span class="meta-label">开始时间</span>
            <span class="mono">{{ relativeDate(instanceInfo.startTime) }}</span>
          </div>
          <div class="meta-item" v-if="instanceInfo?.endTime">
            <span class="meta-label">结束时间</span>
            <span class="mono">{{ relativeDate(instanceInfo.endTime) }}</span>
          </div>
          <div class="meta-item" v-if="instanceInfo?.duration != null">
            <span class="meta-label">总耗时</span>
            <span class="mono">{{ formatDuration(instanceInfo.duration) }}</span>
          </div>
          <div class="meta-item" v-if="instanceInfo?.runTimes">
            <span class="meta-label">重试次数</span>
            <span class="mono">{{ instanceInfo.runTimes }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 任务时间线 -->
    <div class="tasks-card glass-card">
      <div class="section-header">
        <span class="section-title">执行节点</span>
        <span class="section-count" v-if="tasks.length">{{ tasks.length }} 个任务</span>
        <span v-if="hasRunning" class="running-hint">
          <span class="pulse-dot-sm" style="--pulse-color: var(--color-primary);"></span>
          自动刷新中
        </span>
      </div>

      <div v-if="loading && !tasks.length" class="section-empty"><a-spin /></div>
      <div v-else-if="!tasks.length" class="section-empty">
        <a-empty description="暂无节点数据" />
      </div>
      <div v-else class="timeline">
        <div v-for="(task, idx) in tasks" :key="task.id" class="tl-item">
          <div class="tl-left">
            <div class="tl-dot"
              :style="{ background: stateInfo(task.state).color }"
              :class="{ 'tl-dot--pulse': task.state === 'RUNNING' }">
            </div>
            <div v-if="idx < tasks.length - 1" class="tl-line"></div>
          </div>
          <div class="tl-card">
            <div class="tl-card__header">
              <span class="tl-task-type">{{ task.taskType || 'TASK' }}</span>
              <span class="tl-name">{{ task.name }}</span>
              <span class="tl-badge"
                :style="{ color: stateInfo(task.state).color, background: stateInfo(task.state).bg }">
                {{ stateInfo(task.state).label }}
              </span>
            </div>
            <div class="tl-card__meta">
              <span v-if="task.startTime">开始 {{ relativeDate(task.startTime) }}</span>
              <span v-if="task.endTime">结束 {{ relativeDate(task.endTime) }}</span>
              <span>耗时 {{ formatDuration(task.duration) }}</span>
            </div>
            <div class="tl-card__actions">
              <a-button type="text" size="mini" @click="viewLog(task.id)">查看日志</a-button>
            </div>
          </div>
        </div>
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

<script lang="ts">
import { IconLeft } from '@arco-design/web-vue/es/icon'
export default { components: { IconLeft } }
</script>

<style scoped>
.detail-page { padding: var(--space-5); max-width: 960px; animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

/* 头部卡片 */
.detail-header-card { padding: var(--space-5) var(--space-6); margin-bottom: var(--space-5); }
.header-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-4); }
.header-actions { display: flex; gap: var(--space-2); }
.header-info { display: flex; flex-direction: column; gap: var(--space-3); }
.header-title-row { display: flex; align-items: center; gap: var(--space-3); }
.instance-title { font-size: var(--font-size-xl); font-weight: var(--font-weight-semibold); color: var(--color-text-primary); }
.instance-id { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }
.state-badge-lg {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 14px; border-radius: var(--radius-full);
  font-size: var(--font-size-sm); font-weight: 600;
}
.header-meta { display: flex; gap: var(--space-6); flex-wrap: wrap; }
.meta-item { display: flex; flex-direction: column; gap: 2px; }
.meta-label { font-size: 11px; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: 0.5px; }
.meta-item .mono { font-size: var(--font-size-sm); color: var(--color-text-secondary); }

/* 触发类型标签 */
.trigger-tag { display: inline-block; padding: 1px 8px; border-radius: var(--radius-full); font-size: 11px; font-weight: 500; }
.trigger--manual     { background: var(--color-bg-elevated); color: var(--color-text-secondary); }
.trigger--schedule   { background: #EFF6FF; color: #2563EB; }
.trigger--complement { background: #F5F3FF; color: #8B5CF6; }

/* 任务卡片 */
.tasks-card { padding: var(--space-5) var(--space-6); }
.section-header { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-5); }
.section-title { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); color: var(--color-text-primary); }
.section-count { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.running-hint { display: inline-flex; align-items: center; gap: 5px; font-size: var(--font-size-xs); color: var(--color-primary); margin-left: auto; }
.section-empty { display: flex; align-items: center; justify-content: center; height: 120px; }

/* 时间线 */
.timeline { display: flex; flex-direction: column; }
.tl-item { display: flex; gap: var(--space-4); }
.tl-left { display: flex; flex-direction: column; align-items: center; width: 20px; flex-shrink: 0; }
.tl-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; margin-top: 6px; }
.tl-dot--pulse { animation: pulse-ring 1.5s ease-out infinite; }
.tl-line { flex: 1; width: 2px; background: var(--color-border); min-height: 20px; margin: 4px 0; }

.tl-card { flex: 1; padding-bottom: var(--space-5); }
.tl-card__header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.tl-task-type {
  font-size: 10px; font-family: var(--font-family-mono);
  background: var(--color-bg-elevated); color: var(--color-text-tertiary);
  padding: 2px 6px; border-radius: 3px; flex-shrink: 0;
}
.tl-name { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); }
.tl-badge { padding: 2px 10px; border-radius: 10px; font-size: var(--font-size-xs); font-weight: 500; }
.tl-card__meta { display: flex; gap: var(--space-4); font-size: var(--font-size-xs); color: var(--color-text-tertiary); margin-bottom: var(--space-2); }
.tl-card__actions { display: flex; gap: var(--space-2); }

.pulse-dot-sm { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; animation: pulse-ring 1.5s ease-out infinite; }
@keyframes pulse-ring {
  0%   { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.4); }
  70%  { box-shadow: 0 0 0 8px rgba(37, 99, 235, 0); }
  100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0); }
}

.mono { font-family: var(--font-family-mono); }

.log-pre {
  margin: 0; font-size: var(--font-size-xs); line-height: 1.7;
  white-space: pre-wrap; word-break: break-all;
  background: #1a1a2e; color: #e2e8f0;
  padding: var(--space-4); border-radius: var(--radius-md);
  max-height: 520px; overflow-y: auto; font-family: var(--font-family-mono);
}
</style>
