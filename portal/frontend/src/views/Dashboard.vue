<template>
  <div class="dashboard">
    <!-- 欢迎横幅 -->
    <div class="welcome-banner">
      <div class="welcome-left">
        <div class="welcome-accent"></div>
        <div class="welcome-info">
          <h2 class="welcome-title">欢迎回来，{{ userInfo?.real_name || '管理员' }}</h2>
          <p class="welcome-desc">数据中台 MVP · 金融行业离线数据统一工作台</p>
        </div>
      </div>
      <div class="welcome-time">{{ currentTime }}</div>
    </div>

    <!-- 统计卡片 -->
    <div class="stat-grid">
      <div v-for="(stat, i) in statCards" :key="i" class="stat-card glass-card" @click="$router.push(stat.path)">
        <div class="stat-color-bar" :style="{ background: stat.color }"></div>
        <div class="stat-body">
          <div class="stat-label">{{ stat.label }}</div>
          <div class="stat-value" :style="{ color: stat.color }">{{ stat.value }}</div>
          <div class="stat-desc">{{ stat.desc }}</div>
        </div>
      </div>
    </div>

    <!-- 昨日调度概览 -->
    <div class="glass-card overview-section">
      <h3 class="section-title">昨日调度概览</h3>
      <div class="overview-grid">
        <div class="overview-chart">
          <div class="donut-wrap">
            <svg viewBox="0 0 120 120" class="donut-svg">
              <circle cx="60" cy="60" r="50" fill="none" stroke="#F2F3F5" stroke-width="12"/>
              <circle v-if="yesterdayData.total > 0" cx="60" cy="60" r="50" fill="none"
                :stroke="yesterdayData.failure > 0 ? '#F53F3F' : '#00B42A'"
                stroke-width="12" stroke-linecap="round"
                :stroke-dasharray="donutDash" stroke-dashoffset="0"
                transform="rotate(-90 60 60)"/>
            </svg>
            <div class="donut-center">
              <div class="donut-number">{{ yesterdayData.total }}</div>
              <div class="donut-label">总执行</div>
            </div>
          </div>
        </div>
        <div class="overview-details">
          <div class="detail-row">
            <span class="dot success"></span>
            <span class="detail-label">成功</span>
            <span class="detail-value">{{ yesterdayData.success }}</span>
          </div>
          <div class="detail-row">
            <span class="dot failure"></span>
            <span class="detail-label">失败</span>
            <span class="detail-value">{{ yesterdayData.failure }}</span>
          </div>
          <div class="detail-row">
            <span class="dot pending"></span>
            <span class="detail-label">待运行</span>
            <span class="detail-value">{{ yesterdayData.pending }}</span>
          </div>
        </div>
        <div class="overview-trend">
          <div class="trend-title">近 7 日趋势</div>
          <div class="trend-bars">
            <div v-for="(v, i) in stats.workflow_trend" :key="i" class="trend-bar-wrap">
              <div class="trend-bar" :style="{ height: trendHeight(v) + 'px', background: v > 0 ? '#2B5AED' : '#E5E8ED' }"></div>
              <div class="trend-day">{{ trendLabel(i) }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 最近运行 + 快捷操作 -->
    <div class="content-grid">
      <div class="glass-card recent-section">
        <div class="section-header">
          <h3 class="section-title">最近运行</h3>
          <a-button type="text" size="small" @click="$router.push('/scheduler/history')">查看全部</a-button>
        </div>
        <div v-if="recentRuns.length" class="recent-list">
          <div v-for="run in recentRuns" :key="run.id" class="recent-item">
            <span class="run-dot" :class="runStatusClass(run.state)"></span>
            <span class="run-name">{{ run.name }}</span>
            <span class="run-status" :class="runStatusClass(run.state)">{{ runStatusText(run.state) }}</span>
            <span class="run-time">{{ formatRunTime(run.endTime || run.startTime) }}</span>
          </div>
        </div>
        <div v-else class="recent-empty">暂无运行记录</div>
      </div>

      <div class="glass-card quick-section">
        <h3 class="section-title">快捷操作</h3>
        <div class="quick-grid">
          <div v-for="item in quickActions" :key="item.title" class="quick-item" @click="$router.push(item.path)">
            <div class="quick-icon" :style="{ background: item.bg }">
              <component :is="item.icon" style="font-size: 18px;" :style="{ color: item.color }" />
            </div>
            <span class="quick-label">{{ item.title }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useUserStore } from '../stores/user'
import { getDashboardStats, getDSInstances } from '../api'
import {
  IconLink, IconSync, IconCalendar, IconApps,
  IconBranch, IconNotification,
} from '@arco-design/web-vue/es/icon'
import dayjs from 'dayjs'

const userStore = useUserStore()
const userInfo = computed(() => userStore.userInfo)
const currentTime = ref(new Date().toLocaleString('zh-CN'))

const stats = reactive({
  datasource_total: 0, datasource_active: 0,
  task_total: 0, task_active: 0,
  workflow_total: 0, word_root_count: 0,
  yesterday_runs: 0, yesterday_success: 0,
  yesterday_failure: 0, yesterday_pending: 0,
  workflow_trend: [] as number[],
})

const recentRuns = ref<any[]>([])

const yesterdayData = computed(() => ({
  total: stats.yesterday_runs,
  success: stats.yesterday_success,
  failure: stats.yesterday_failure,
  pending: stats.yesterday_pending,
}))

const donutDash = computed(() => {
  const d = yesterdayData.value
  if (d.total === 0) return '0 314'
  const circumference = 2 * Math.PI * 50
  const successLen = (d.success / d.total) * circumference
  return `${successLen} ${circumference}`
})

const statCards = computed(() => [
  { label: '数据源', value: stats.datasource_total, desc: `${stats.datasource_active} 个可用`, color: '#2B5AED', path: '/datasources' },
  { label: '组件', value: stats.task_total, desc: `${stats.task_active} 个运行中`, color: '#00B42A', path: '/sql-dev' },
  { label: '工作流', value: stats.workflow_total, desc: '调度编排', color: '#FF7D00', path: '/workflows' },
  { label: '词根', value: stats.word_root_count, desc: '命名规范', color: '#00C9A7', path: '/field-assets' },
  { label: '昨日执行', value: stats.yesterday_runs, desc: stats.yesterday_failure > 0 ? `${stats.yesterday_failure} 个失败` : '全部成功', color: stats.yesterday_failure > 0 ? '#F53F3F' : '#722ED1', path: '/scheduler/history' },
])

function trendHeight(v: number) {
  const max = Math.max(...stats.workflow_trend, 1)
  return Math.max(4, (v / max) * 48)
}

function trendLabel(i: number) {
  const d = dayjs().subtract(6 - i, 'day')
  return d.format('dd')
}

const quickActions = [
  { title: '新建工作流', path: '/workflows', bg: 'rgba(255,125,0,0.08)', color: '#FF7D00', icon: IconBranch },
  { title: '新建组件', path: '/sql-dev', bg: 'rgba(0,180,42,0.08)', color: '#00B42A', icon: IconSync },
  { title: '数据源管理', path: '/datasources', bg: 'rgba(43,90,237,0.08)', color: '#2B5AED', icon: IconLink },
  { title: '数据目录', path: '/data-assets', bg: 'rgba(0,201,167,0.08)', color: '#00C9A7', icon: IconApps },
  { title: '运行实例', path: '/scheduler/history', bg: 'rgba(114,46,209,0.08)', color: '#722ED1', icon: IconCalendar },
  { title: '监控规则', path: '/alerts', bg: 'rgba(245,63,63,0.08)', color: '#F53F3F', icon: IconNotification },
]

function runStatusClass(state: string) {
  if (!state) return 'unknown'
  const s = state.toUpperCase()
  if (s.includes('SUCCESS')) return 'success'
  if (s.includes('FAIL') || s.includes('STOP')) return 'failure'
  if (s.includes('RUNNING')) return 'running'
  return 'pending'
}

function runStatusText(state: string) {
  if (!state) return '未知'
  const s = state.toUpperCase()
  if (s.includes('SUCCESS')) return '成功'
  if (s.includes('FAIL')) return '失败'
  if (s.includes('STOP')) return '停止'
  if (s.includes('RUNNING')) return '运行中'
  return '等待'
}

function formatRunTime(t: string) {
  if (!t) return ''
  const d = dayjs(t)
  const now = dayjs()
  const diff = now.diff(d, 'minute')
  if (diff < 1) return '刚刚'
  if (diff < 60) return `${diff}分钟前`
  if (diff < 1440) return `${Math.floor(diff / 60)}小时前`
  return d.format('MM-DD HH:mm')
}

let clockTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  clockTimer = setInterval(() => { currentTime.value = new Date().toLocaleString('zh-CN') }, 1000)
  try {
    const res: any = await getDashboardStats()
    Object.assign(stats, res)
  } catch {}
  try {
    const res: any = await getDSInstances({ pageSize: 5, pageNo: 1 })
    recentRuns.value = res?.totalList?.slice(0, 5) || []
  } catch {}
})

onUnmounted(() => {
  if (clockTimer) { clearInterval(clockTimer); clockTimer = null }
})
</script>

<style scoped>
.dashboard { max-width: 1200px; animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.welcome-banner { background: #FFFFFF; border: 1px solid #E5E8ED; border-radius: 10px; padding: 24px 28px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
.welcome-left { display: flex; align-items: stretch; gap: 16px; }
.welcome-accent { width: 4px; border-radius: 2px; background: linear-gradient(180deg, #2B5AED, #00C9A7); }
.welcome-title { margin: 0 0 4px; font-size: 20px; font-weight: 600; color: #1D2129; }
.welcome-desc { margin: 0; font-size: 13px; color: #86909C; }
.welcome-time { font-size: 13px; color: #86909C; font-family: 'JetBrains Mono', monospace; }
.stat-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin-bottom: 20px; }
.stat-card { padding: 0; display: flex; cursor: pointer; transition: transform 0.15s, box-shadow 0.15s; overflow: hidden; }
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
.stat-color-bar { width: 4px; flex-shrink: 0; border-radius: 10px 0 0 10px; }
.stat-body { padding: 16px; flex: 1; }
.stat-label { font-size: 12px; color: #86909C; margin-bottom: 6px; }
.stat-value { font-size: 26px; font-weight: 700; font-family: 'DM Sans', 'Inter', sans-serif; line-height: 1.2; }
.stat-desc { font-size: 11px; color: #86909C; margin-top: 4px; }
.overview-section { padding: 20px; margin-bottom: 20px; }
.section-title { margin: 0 0 16px; font-size: 15px; font-weight: 600; color: #1D2129; }
.overview-grid { display: flex; gap: 32px; align-items: center; }
.donut-wrap { position: relative; width: 100px; height: 100px; }
.donut-svg { width: 100%; height: 100%; }
.donut-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.donut-number { font-size: 22px; font-weight: 700; color: #1D2129; }
.donut-label { font-size: 10px; color: #86909C; }
.overview-details { display: flex; flex-direction: column; gap: 10px; }
.detail-row { display: flex; align-items: center; gap: 8px; }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.dot.success { background: #00B42A; }
.dot.failure { background: #F53F3F; }
.dot.pending { background: #FF7D00; }
.detail-label { font-size: 13px; color: #4E5969; min-width: 40px; }
.detail-value { font-size: 15px; font-weight: 600; color: #1D2129; }
.overview-trend { flex: 1; margin-left: 24px; }
.trend-title { font-size: 12px; color: #86909C; margin-bottom: 8px; }
.trend-bars { display: flex; gap: 8px; align-items: flex-end; height: 64px; }
.trend-bar-wrap { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1; }
.trend-bar { width: 100%; max-width: 32px; border-radius: 3px 3px 0 0; transition: height 0.3s; }
.trend-day { font-size: 10px; color: #C9CDD4; }
.content-grid { display: grid; grid-template-columns: 1.2fr 1fr; gap: 16px; margin-bottom: 20px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header .section-title { margin: 0; }
.recent-section { padding: 20px; }
.recent-list { display: flex; flex-direction: column; }
.recent-item { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid #F2F3F5; }
.recent-item:last-child { border-bottom: none; }
.run-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.run-dot.success { background: #00B42A; }
.run-dot.failure { background: #F53F3F; }
.run-dot.running { background: #165DFF; animation: pulse 1.5s infinite; }
.run-dot.pending { background: #FF7D00; }
.run-dot.unknown { background: #C9CDD4; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
.run-name { flex: 1; font-size: 13px; color: #1D2129; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-status { font-size: 12px; font-weight: 500; }
.run-status.success { color: #00B42A; }
.run-status.failure { color: #F53F3F; }
.run-status.running { color: #165DFF; }
.run-status.pending { color: #FF7D00; }
.run-time { font-size: 11px; color: #C9CDD4; white-space: nowrap; }
.recent-empty { padding: 24px 0; text-align: center; color: #86909C; font-size: 13px; }
.quick-section { padding: 20px; }
.quick-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.quick-item { display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-radius: 8px; cursor: pointer; transition: background 0.15s; }
.quick-item:hover { background: #F7F8FA; }
.quick-icon { width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; }
.quick-label { font-size: 13px; color: #1D2129; font-weight: 500; }
@media (max-width: 1200px) { .stat-grid { grid-template-columns: repeat(3, 1fr); } .content-grid { grid-template-columns: 1fr; } }
</style>