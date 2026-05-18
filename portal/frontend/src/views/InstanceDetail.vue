<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
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

const STATE_MAP: Record<string, { text: string; color: string; bg: string }> = {
  SUCCESS:           { text: '成功',   color: '#00b42a', bg: '#e8ffea' },
  FAILURE:           { text: '失败',   color: '#f53f3f', bg: '#ffece8' },
  RUNNING_EXECUTION: { text: '运行中', color: '#165dff', bg: '#e8f3ff' },
  STOP:              { text: '停止',   color: '#86909c', bg: '#f2f3f5' },
  KILL:              { text: '已终止', color: '#ff7d00', bg: '#fff7e8' },
  NEED_FAULT_TOLERANCE: { text: '容错中', color: '#ff7d00', bg: '#fff7e8' },
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

function stateInfo(state: string) {
  return STATE_MAP[state] || { text: state, color: '#86909c', bg: '#f2f3f5' }
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
                {{ stateInfo(task.state).text }}
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
.detail-page { padding: 20px; max-width: 900px; }

.detail-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
.detail-title { font-size: 18px; font-weight: 600; flex: 1; }

.detail-body { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 24px; }
.section-title { font-size: 14px; font-weight: 600; color: #4e5969; margin-bottom: 20px; }
.section-empty { display: flex; align-items: center; justify-content: center; height: 120px; }

.timeline { display: flex; flex-direction: column; }
.tl-item { display: flex; gap: 16px; }
.tl-left { display: flex; flex-direction: column; align-items: center; width: 20px; flex-shrink: 0; }
.tl-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; margin-top: 6px; }
.tl-dot--pulse { animation: pulse 1.5s ease-out infinite; }
.tl-line { flex: 1; width: 2px; background: #e5e7eb; min-height: 20px; margin: 4px 0; }

.tl-card { flex: 1; padding-bottom: 20px; }
.tl-card__header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.tl-name { font-size: 14px; font-weight: 600; }
.tl-badge { padding: 2px 10px; border-radius: 10px; font-size: 12px; font-weight: 500; }
.tl-card__meta { display: flex; gap: 16px; font-size: 12px; color: #86909c; margin-bottom: 8px; }
.tl-card__actions { display: flex; gap: 8px; }

@keyframes pulse {
  0%   { box-shadow: 0 0 0 0 rgba(22, 93, 255, 0.4); }
  70%  { box-shadow: 0 0 0 8px rgba(22, 93, 255, 0); }
  100% { box-shadow: 0 0 0 0 rgba(22, 93, 255, 0); }
}

.log-pre { margin: 0; font-size: 12px; line-height: 1.7; white-space: pre-wrap; word-break: break-all; background: #1a1a2e; color: #e2e8f0; padding: 16px; border-radius: 6px; max-height: 520px; overflow-y: auto; font-family: 'JetBrains Mono', Consolas, monospace; }
</style>
