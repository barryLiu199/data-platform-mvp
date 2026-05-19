<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { getLifecycleStatus } from '../constants/status'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import { getScheduledWorkflows, scheduleWorkflowOnline, scheduleWorkflowOffline } from '../api'

interface ScheduledItem {
  id: number
  name: string
  cron_expression: string
  schedule_status: string
  status: string
  next_fire_time: string | null
  ds_process_code: number | null
}

const router = useRouter()
const items = ref<ScheduledItem[]>([])
const loading = ref(false)
const switchLoading = ref<Record<number, boolean>>({})

function getWfStatus(status: string) {
  return getLifecycleStatus(status)
}

onMounted(() => loadData())

async function loadData() {
  loading.value = true
  try {
    const res: any = await getScheduledWorkflows()
    items.value = res.items || []
  } catch (e: any) {
    Message.error('加载调度任务失败：' + (e?.response?.data?.detail || e?.message || '未知错误'))
    items.value = []
  } finally {
    loading.value = false }
}

async function toggleSchedule(item: ScheduledItem) {
  if (item.status !== 'online') {
    Message.warning('请先发布工作流，才能开启调度')
    return
  }
  switchLoading.value[item.id] = true
  try {
    if (item.schedule_status === 'ONLINE') {
      await scheduleWorkflowOffline(item.id)
      item.schedule_status = 'OFFLINE'
      Message.success('调度已关闭')
    } else {
      await scheduleWorkflowOnline(item.id)
      item.schedule_status = 'ONLINE'
      Message.success('调度已开启')
    }
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '操作失败')
  } finally {
    switchLoading.value[item.id] = false
  }
}

function goToEditor(item: ScheduledItem) {
  router.push(`/workflows/${item.id}/edit`)
}

function formatNextFireTime(t: string | null): string {
  if (!t) return '-'
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  const now = new Date()
  const diff = d.getTime() - now.getTime()
  const hh = d.getHours().toString().padStart(2, '0')
  const mm = d.getMinutes().toString().padStart(2, '0')
  if (diff < 0) return `${hh}:${mm}（已过期）`
  const days = Math.floor(diff / 86400000)
  if (days === 0) return `今天 ${hh}:${mm}`
  if (days === 1) return `明天 ${hh}:${mm}`
  return `${d.getMonth()+1}/${d.getDate()} ${hh}:${mm}`
}
</script>

<template>
  <div class="tasks-page">
    <PageHeader title="调度任务" description="管理所有配置了定时调度的工作流">
      <template #actions>
        <a-button @click="loadData" :loading="loading" size="small">刷新</a-button>
      </template>
    </PageHeader>

    <div class="glass-card tasks-table-wrap">
      <div v-if="loading && !items.length" class="tasks-empty"><a-spin /></div>
      <EmptyState v-else-if="!items.length" description="暂无调度任务，请在工作流编辑器中配置 CRON 表达式" />
      <table v-else class="tasks-table">
        <thead>
          <tr>
            <th>工作流名称</th>
            <th style="width:160px">CRON 表达式</th>
            <th style="width:140px">下次执行</th>
            <th style="width:100px">工作流状态</th>
            <th style="width:90px">调度开关</th>
            <th style="width:80px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id" class="task-row">
            <td class="name-cell">{{ item.name }}</td>
            <td>
              <code class="cron-code">{{ item.cron_expression }}</code>
            </td>
            <td class="next-time-cell">{{ formatNextFireTime(item.next_fire_time) }}</td>
            <td>
              <span
                class="wf-status"
                :style="{ color: getWfStatus(item.status).color }"
              >
                <span class="wf-status__dot" :style="{ background: getWfStatus(item.status).color }"></span>
                {{ getWfStatus(item.status).label }}
              </span>
            </td>
            <td>
              <a-tooltip :content="item.status !== 'online' ? '请先发布工作流' : ''" :disabled="item.status === 'online'">
                <a-switch
                  :model-value="item.schedule_status === 'ONLINE'"
                  :disabled="item.status !== 'online'"
                  :loading="switchLoading[item.id]"
                  @change="toggleSchedule(item)"
                />
              </a-tooltip>
            </td>
            <td>
              <a-button type="text" size="mini" @click="goToEditor(item)">编辑</a-button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.tasks-page { padding: var(--space-5); }

.tasks-table-wrap { overflow: hidden; }
.tasks-empty { display: flex; align-items: center; justify-content: center; height: 200px; }

.tasks-table { width: 100%; border-collapse: collapse; font-size: var(--font-size-sm); }
.tasks-table thead tr { background: var(--color-bg-elevated); }
.tasks-table th { padding: 10px var(--space-4); text-align: left; font-weight: 500; color: var(--color-text-secondary); border-bottom: 1px solid var(--color-border); white-space: nowrap; }
.tasks-table td { padding: var(--space-3) var(--space-4); border-bottom: 1px solid var(--color-border-subtle); vertical-align: middle; }
.task-row:last-child td { border-bottom: none; }
.task-row:hover { background: var(--color-bg-elevated); }

.name-cell { font-weight: 500; }
.cron-code { font-size: var(--font-size-xs); background: var(--color-bg-elevated); padding: 3px 8px; border-radius: var(--radius-sm); font-family: var(--font-family-mono); color: var(--color-text-primary); }
.next-time-cell { color: var(--color-text-secondary); font-size: var(--font-size-sm); }

.wf-status { display: flex; align-items: center; gap: 5px; font-size: var(--font-size-sm); }
.wf-status__dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
</style>
