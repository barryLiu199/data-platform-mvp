<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { getExecutionStatus } from '../constants/status'
import { getDSInstanceTasks, getDSTaskLog, rerunDSInstance } from '../api'

interface Task {
  id: number; name: string; state: string
  startTime: string; endTime: string; duration: string
}

const route = useRoute()
const router = useRouter()
const instanceId = Number(route.params.id)

const tasks = ref<Task[]>([])
const loading = ref(false)
const logVisible = ref(false)
const logContent = ref('')
const logLoading = ref(false)
const rerunLoading = ref(false)
let rerunTimer: ReturnType<typeof setTimeout> | null = null

function stateInfo(state: string) {
  return getExecutionStatus(state)
}

onMounted(() => loadTasks())
onUnmounted(() => {
  if (rerunTimer) clearTimeout(rerunTimer)
})

async function loadTasks() {
  loading.value = true
  try {
    const res: any = await getDSInstanceTasks(instanceId)
    const list = Array.isArray(res) ? res : (res.taskList || res.list || [])
    tasks.value = list.map((t: any) => ({
      id: t.id,
      name: t.name,
      state: t.state,
      startTime: t.startTime ? formatTime(t.startTime) : '-',
      endTime: t.endTime ? formatTime(t.endTime) : '-',
      duration: t.duration != null ? formatDuration(t.duration) : '-',
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
    rerunTimer = setTimeout(loadTasks, 1500)
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '重跑失败')
  } finally { rerunLoading.value = false }
}

function formatTime(ts: string): string {
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatDuration(s: number): string {
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return m < 60 ? `${m}m${s % 60}s` : `${Math.floor(m / 60)}h${m % 60}m`
}
</script>

<template>
  <div class="detail-page">
    <!-- 顶部导航 -->
    <div class="detail-header">
      <a-button type="text" @click="router.back()">← 返回</a-button>
      <span class="detail-title">实例详情 #{{ instanceId }}</span>
      <a-button type="primary" size="small" :loading="rerunLoading" @click="handleRerun">重跑</a-button>
    </div>

    <!-- 任务时间线 -->
    <div class="detail-body">
      <div class="section-title">执行节点</div>
      <div v-if="loading" class="section-empty"><a-spin /></div>
      <div v-else-if="!tasks.length" class="section-empty">
        <a-empty description="暂无节点数据" />
      </div>
      <div v-else class="timeline">
        <div v-for="(task, idx) in tasks" :key="task.id" class="tl-item">
          <div class="tl-left">
            <div class="tl-dot"
              :style="{ background: stateInfo(task.state).color }"
              :class="{ 'tl-dot--pulse': task.state === 'RUNNING_EXECUTION' }">
            </div>
            <div v-if="idx < tasks.length - 1" class="tl-line"></div>
          </div>
          <div class="tl-card">
            <div class="tl-card__header">
              <span class="tl-name">{{ task.name }}</span>
              <span class="tl-badge"
                :style="{ color: stateInfo(task.state).color, background: stateInfo(task.state).bg }">
                {{ stateInfo(task.state).label }}
              </span>
            </div>
            <div class="tl-card__meta">
              <span>开始 {{ task.startTime }}</span>
              <span>结束 {{ task.endTime }}</span>
              <span>耗时 {{ task.duration }}</span>
            </div>
            <div class="tl-card__actions">
              <a-button type="text" size="mini" @click="viewLog(task.id)">查看日志</a-button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 日志弹窗 -->
    <a-modal v-model:visible="logVisible" title="任务日志" :width="860" :footer="false">
      <a-spin :loading="logLoading" style="width:100%; min-height:200px">
        <pre class="log-pre">{{ logContent || '加载中...' }}</pre>
      </a-spin>
    </a-modal>
  </div>
</template>

<style scoped>
.detail-page { padding: var(--space-5); max-width: 900px; }

.detail-header { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-6); }
.detail-title { font-size: var(--font-size-xl); font-weight: var(--font-weight-semibold); flex: 1; }

.detail-body { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-6); }
.section-title { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); color: var(--color-text-secondary); margin-bottom: var(--space-5); }
.section-empty { display: flex; align-items: center; justify-content: center; height: 120px; }

.timeline { display: flex; flex-direction: column; }
.tl-item { display: flex; gap: var(--space-4); }
.tl-left { display: flex; flex-direction: column; align-items: center; width: 20px; flex-shrink: 0; }
.tl-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; margin-top: 6px; }
.tl-dot--pulse { animation: pulse 1.5s ease-out infinite; }
.tl-line { flex: 1; width: 2px; background: var(--color-border); min-height: 20px; margin: 4px 0; }

.tl-card { flex: 1; padding-bottom: var(--space-5); }
.tl-card__header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.tl-name { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); }
.tl-badge { padding: 2px 10px; border-radius: 10px; font-size: var(--font-size-xs); font-weight: 500; }
.tl-card__meta { display: flex; gap: var(--space-4); font-size: var(--font-size-xs); color: var(--color-text-tertiary); margin-bottom: var(--space-2); }
.tl-card__actions { display: flex; gap: var(--space-2); }

@keyframes pulse {
  0%   { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.4); }
  70%  { box-shadow: 0 0 0 8px rgba(37, 99, 235, 0); }
  100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0); }
}

.log-pre { margin: 0; font-size: var(--font-size-xs); line-height: 1.7; white-space: pre-wrap; word-break: break-all; background: #1a1a2e; color: #e2e8f0; padding: var(--space-4); border-radius: var(--radius-md); max-height: 520px; overflow-y: auto; font-family: var(--font-family-mono); }
</style>
