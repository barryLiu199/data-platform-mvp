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
          <div class="stat-icon" :style="{ background: stat.iconBg }">
            <component :is="stat.icon" :style="{ color: stat.color, fontSize: '18px' }" />
          </div>
          <div class="stat-content">
            <div class="stat-label">{{ stat.label }}</div>
            <div class="stat-value" :style="{ color: stat.color }">{{ stat.value }}</div>
            <div class="stat-desc">{{ stat.desc }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 调度概览 -->
    <div class="glass-card overview-section">
      <div class="section-header">
        <h3 class="section-title">调度概览</h3>
        <a-range-picker
          v-model="overviewDateRange"
          style="width: 260px"
          format="YYYY-MM-DD"
          @change="onDateChange"
        />
      </div>
      <div class="overview-body">
        <!-- 左：饼图 -->
        <div class="overview-chart">
          <SchedulePieChart :data="pieChartData" />
        </div>
        <!-- 右：状态明细网格 -->
        <div class="overview-detail-grid">
          <div
            v-for="item in pieChartData"
            :key="item.key"
            class="detail-card"
          >
            <div class="detail-dot" :style="{ background: item.color, boxShadow: `0 0 8px ${item.color}40` }"></div>
            <div class="detail-info">
              <div class="detail-count" :style="{ color: item.color }">{{ item.value }}</div>
              <div class="detail-label">{{ item.name }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部三栏：趋势 + 最近运行 + 快捷操作 -->
    <div class="bottom-grid">
      <!-- 7日趋势 -->
      <div class="glass-card trend-section">
        <h3 class="section-title">近 7 日趋势</h3>
        <div class="trend-bars">
          <div v-for="(v, i) in stats.workflow_trend" :key="i" class="trend-bar-wrap">
            <div class="trend-bar" :style="{ height: trendHeight(v) + 'px' }">
              <div class="trend-tooltip">{{ v }}</div>
            </div>
            <div class="trend-day">{{ trendLabel(i) }}</div>
          </div>
        </div>
      </div>

      <!-- 最近运行 -->
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

      <!-- 快捷操作 -->
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
import { getDashboardStats, getDSInstances, getScheduleOverview } from '../api'
import { EXECUTION_STATUS } from '../constants/status'
import SchedulePieChart from '../components/SchedulePieChart.vue'
import {
  IconLink, IconSync, IconCalendar, IconApps,
  IconBranch, IconNotification, IconCode,
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

// 调度概览
const overviewDateRange = ref<string[]>([
  dayjs().subtract(1, 'day').format('YYYY-MM-DD'),
  dayjs().subtract(1, 'day').format('YYYY-MM-DD'),
])
const overviewCategories = ref<Array<{ name: string; key: string; count: number }>>([])
const overviewTotal = ref(0)

// 状态 key → 颜色映射
const STATUS_COLORS: Record<string, string> = {
  success: EXECUTION_STATUS.SUCCESS.color,
  submitted: EXECUTION_STATUS.SUBMITTED.color,
  waiting: EXECUTION_STATUS.WAIT.color,
  running: EXECUTION_STATUS.RUNNING.color,
  failure: EXECUTION_STATUS.FAILURE.color,
  stopped: EXECUTION_STATUS.STOP.color,
}

const pieChartData = computed(() =>
  overviewCategories.value.map(c => ({
    key: c.key,
    name: c.name,
    value: c.count,
    color: STATUS_COLORS[c.key] || '#94A3B8',
  }))
)

async function loadOverview() {
  try {
    const [startDate, endDate] = overviewDateRange.value
    const res: any = await getScheduleOverview({
      start_date: startDate,
      end_date: endDate,
    })
    overviewCategories.value = res?.categories || []
    overviewTotal.value = res?.total || 0
  } catch {}
}

function onDateChange() {
  loadOverview()
}

const statCards = computed(() => [
  { label: '数据源', value: stats.datasource_total, desc: `${stats.datasource_active} 个可用`, color: 'var(--color-primary)', iconBg: 'var(--color-primary-light)', icon: IconLink, path: '/datasources' },
  { label: '组件', value: stats.task_total, desc: `${stats.task_active} 个运行中`, color: 'var(--color-success)', iconBg: 'var(--color-success-light)', icon: IconCode, path: '/sql-dev' },
  { label: '工作流', value: stats.workflow_total, desc: '调度编排', color: 'var(--color-warning)', iconBg: 'var(--color-warning-light)', icon: IconBranch, path: '/workflows' },
  { label: '词根', value: stats.word_root_count, desc: '命名规范', color: 'var(--color-accent)', iconBg: 'var(--color-accent-light)', icon: IconApps, path: '/field-assets' },
  { label: '昨日执行', value: stats.yesterday_runs, desc: stats.yesterday_failure > 0 ? `${stats.yesterday_failure} 个失败` : '全部成功', color: stats.yesterday_failure > 0 ? 'var(--color-danger)' : '#722ED1', iconBg: stats.yesterday_failure > 0 ? 'var(--color-danger-light)' : '#F5F3FF', icon: IconCalendar, path: '/scheduler/history' },
])

function trendHeight(v: number) {
  const max = Math.max(...stats.workflow_trend, 1)
  return Math.max(6, (v / max) * 80)
}

function trendLabel(i: number) {
  const d = dayjs().subtract(6 - i, 'day')
  return d.format('MM/DD')
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
  loadOverview()
})

onUnmounted(() => {
  if (clockTimer) { clearInterval(clockTimer); clockTimer = null }
})
</script>

<style scoped>
.dashboard {
  width: 100%;
  animation: fadeIn 0.3s ease-out;
}
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

/* ─── 欢迎横幅 ─── */
.welcome-banner {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-6) 28px;
  margin-bottom: var(--space-5);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.welcome-left { display: flex; align-items: stretch; gap: var(--space-4); }
.welcome-accent { width: 4px; border-radius: 2px; background: linear-gradient(180deg, var(--color-primary), var(--color-accent)); }
.welcome-title { margin: 0 0 4px; font-size: var(--font-size-xl); font-weight: var(--font-weight-semibold); color: var(--color-text-primary); }
.welcome-desc { margin: 0; font-size: var(--font-size-sm); color: var(--color-text-tertiary); }
.welcome-time { font-size: var(--font-size-sm); color: var(--color-text-tertiary); font-family: var(--font-family-mono); }

/* ─── 统计卡片 ─── */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  margin-bottom: var(--space-5);
}
.stat-card {
  padding: 0;
  display: flex;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  overflow: hidden;
}
.stat-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-lg);
}
.stat-color-bar {
  width: 4px;
  flex-shrink: 0;
  border-radius: var(--radius-lg) 0 0 var(--radius-lg);
}
.stat-body {
  padding: var(--space-4);
  flex: 1;
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}
.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-content { flex: 1; min-width: 0; }
.stat-label { font-size: var(--font-size-xs); color: var(--color-text-tertiary); margin-bottom: 4px; }
.stat-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}
.stat-desc { font-size: 11px; color: var(--color-text-tertiary); margin-top: var(--space-1); }

/* ─── 调度概览 ─── */
.overview-section { padding: var(--space-5) var(--space-6); margin-bottom: var(--space-5); }
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-5);
}
.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}
.overview-body {
  display: flex;
  gap: var(--space-8);
  align-items: center;
}
.overview-chart {
  flex: 0 0 280px;
}
.overview-detail-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
}
.detail-card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  border-radius: var(--radius-lg);
  background: var(--color-bg-base);
  border: 1px solid var(--color-border-subtle);
  transition: background 0.15s, border-color 0.15s, transform 0.15s;
}
.detail-card:hover {
  background: var(--color-bg-elevated);
  border-color: var(--color-border);
  transform: translateY(-1px);
}
.detail-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.detail-info { min-width: 0; }
.detail-count {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}
.detail-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: 2px;
}

/* ─── 底部三栏 ─── */
.bottom-grid {
  display: grid;
  grid-template-columns: 1fr 1.2fr 0.8fr;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

/* ─── 趋势 ─── */
.trend-section { padding: var(--space-5); }
.trend-bars {
  display: flex;
  gap: var(--space-2);
  align-items: flex-end;
  height: 120px;
  padding-top: var(--space-4);
}
.trend-bar-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  flex: 1;
}
.trend-bar {
  width: 100%;
  max-width: 36px;
  border-radius: 4px 4px 0 0;
  background: linear-gradient(180deg, var(--color-primary), var(--color-accent));
  transition: height 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
  position: relative;
  min-height: 4px;
}
.trend-bar:hover {
  opacity: 0.85;
}
.trend-tooltip {
  display: none;
  position: absolute;
  top: -28px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--color-text-primary);
  color: var(--color-text-inverse);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.trend-bar:hover .trend-tooltip { display: block; }
.trend-day {
  font-size: 10px;
  color: var(--color-text-disabled);
  font-variant-numeric: tabular-nums;
}

/* ─── 最近运行 ─── */
.recent-section { padding: var(--space-5); }
.section-header .section-title { margin: 0; }
.recent-list { display: flex; flex-direction: column; }
.recent-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--color-border-subtle);
  transition: background 0.15s;
}
.recent-item:last-child { border-bottom: none; }
.recent-item:hover { background: var(--color-bg-base); margin: 0 -8px; padding-left: 8px; padding-right: 8px; border-radius: var(--radius-md); }
.run-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.run-dot.success { background: var(--color-success); box-shadow: 0 0 6px rgba(22,163,74,0.4); }
.run-dot.failure { background: var(--color-danger); box-shadow: 0 0 6px rgba(220,38,38,0.4); }
.run-dot.running { background: var(--color-primary); animation: pulse 1.5s infinite; }
.run-dot.pending { background: var(--color-warning); }
.run-dot.unknown { background: var(--color-border-strong); }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
.run-name { flex: 1; font-size: var(--font-size-sm); color: var(--color-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-status { font-size: var(--font-size-xs); font-weight: 500; padding: 2px 8px; border-radius: var(--radius-full); }
.run-status.success { color: var(--color-success); background: var(--color-success-light); }
.run-status.failure { color: var(--color-danger); background: var(--color-danger-light); }
.run-status.running { color: var(--color-primary); background: var(--color-primary-light); }
.run-status.pending { color: var(--color-warning); background: var(--color-warning-light); }
.run-time { font-size: 11px; color: var(--color-text-disabled); white-space: nowrap; font-family: var(--font-family-mono); }
.recent-empty { padding: var(--space-6) 0; text-align: center; color: var(--color-text-tertiary); font-size: var(--font-size-sm); }

/* ─── 快捷操作 ─── */
.quick-section { padding: var(--space-5); }
.quick-grid { display: grid; grid-template-columns: 1fr; gap: 6px; }
.quick-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: var(--space-3) 14px;
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: background 0.15s, transform 0.15s;
}
.quick-item:hover { background: var(--color-bg-elevated); transform: translateX(2px); }
.quick-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
}
.quick-label { font-size: var(--font-size-sm); color: var(--color-text-primary); font-weight: 500; }

/* ─── 响应式 ─── */
@media (max-width: 1400px) {
  .bottom-grid { grid-template-columns: 1fr 1fr; }
  .quick-section { grid-column: span 2; }
  .quick-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 1200px) {
  .stat-grid { grid-template-columns: repeat(3, 1fr); }
  .bottom-grid { grid-template-columns: 1fr; }
  .quick-section { grid-column: auto; }
  .quick-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 768px) {
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
  .overview-body { flex-direction: column; }
  .overview-chart { flex: none; width: 100%; }
  .overview-detail-grid { grid-template-columns: repeat(2, 1fr); }
  .bottom-grid { grid-template-columns: 1fr; }
  .quick-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
