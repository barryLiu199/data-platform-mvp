<template>
  <div class="page">
    <PageHeader :title="rule?.name || '规则详情'" :description="`模板: ${templateName} | 数据源: ${rule?.datasource_name || '-'} | 表: ${rule?.table_name || '-'}`">
      <template #actions>
        <a-button @click="handleExecute" :loading="executing">
          <template #icon><icon-play-arrow /></template>
          执行检查
        </a-button>
        <a-button @click="$router.back()">返回</a-button>
      </template>
    </PageHeader>

    <div v-if="rule" class="content">
      <!-- Info Card -->
      <div class="glass-card info-card">
        <a-descriptions :column="3" bordered size="small">
          <a-descriptions-item label="模板">{{ templateName }}</a-descriptions-item>
          <a-descriptions-item label="严重级别">
            <a-tag :color="severityColor(rule.severity)" size="small">{{ severityLabel(rule.severity) }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="触发方式">{{ rule.trigger_type === 'workflow' ? '工作流触发' : '手动' }}</a-descriptions-item>
          <a-descriptions-item label="最近检查">{{ rule.last_check_time || '-' }}</a-descriptions-item>
          <a-descriptions-item label="最近状态">
            <a-tag v-if="rule.last_check_status === 'pass'" color="green" size="small">通过</a-tag>
            <a-tag v-else-if="rule.last_check_status === 'fail'" color="red" size="small">失败</a-tag>
            <a-tag v-else-if="rule.last_check_status === 'error'" color="orange" size="small">异常</a-tag>
            <span v-else>-</span>
          </a-descriptions-item>
          <a-descriptions-item label="通知">{{ rule.notify_enabled ? '已开启' : '关闭' }}</a-descriptions-item>
        </a-descriptions>
      </div>

      <!-- Config Card -->
      <div class="glass-card config-card">
        <h4>规则配置</h4>
        <pre class="config-json">{{ JSON.stringify(rule.config, null, 2) }}</pre>
      </div>

      <!-- Trend Chart -->
      <div class="glass-card trend-card" v-if="trend.length">
        <h4>检查趋势（近30天）</h4>
        <div class="trend-bar">
          <div
            v-for="(t, i) in trend"
            :key="i"
            class="trend-dot"
            :class="t.status"
            :title="`${t.date}: ${t.status} (${t.actual_value ?? '-'})`"
          />
        </div>
      </div>

      <!-- Recent Results -->
      <div class="glass-card results-card">
        <h4>最近执行记录</h4>
        <a-table :data="rule.recent_results || []" :bordered="false" :pagination="false" size="small" stripe>
          <template #columns>
            <a-table-column title="日期" data-index="check_date" :width="120" />
            <a-table-column title="状态" :width="80">
              <template #cell="{ record }">
                <a-tag :color="record.status === 'pass' ? 'green' : record.status === 'fail' ? 'red' : 'orange'" size="small">
                  {{ record.status }}
                </a-tag>
              </template>
            </a-table-column>
            <a-table-column title="实际值" data-index="actual_value" :width="100" />
            <a-table-column title="耗时(ms)" data-index="duration_ms" :width="100" />
            <a-table-column title="触发方式" data-index="triggered_by" :width="100" />
            <a-table-column title="错误信息" data-index="error_message" ellipsis />
          </template>
        </a-table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { IconPlayArrow } from '@arco-design/web-vue/es/icon'
import PageHeader from '../components/PageHeader.vue'
import { getQualityRule, getQualityTrend, executeQualityRule, getQualityTemplates } from '../api'

const route = useRoute()
const ruleId = Number(route.params.id)

const rule = ref<any>(null)
const trend = ref<any[]>([])
const templates = ref<any[]>([])
const executing = ref(false)

const templateName = computed(() => {
  if (!rule.value) return ''
  return templates.value.find((t: any) => t.code === rule.value.template_code)?.name || rule.value.template_code
})

function severityColor(s: string) {
  return s === 'error' ? 'red' : s === 'warning' ? 'orange' : 'blue'
}
function severityLabel(s: string) {
  return s === 'error' ? '严重' : s === 'warning' ? '警告' : '信息'
}

async function loadRule() {
  const data: any = await getQualityRule(ruleId)
  rule.value = data
}

async function loadTrend() {
  const data: any = await getQualityTrend({ rule_id: ruleId, days: 30 })
  trend.value = data
}

async function handleExecute() {
  executing.value = true
  try {
    await executeQualityRule(ruleId)
    Message.success('已提交执行')
    setTimeout(() => { loadRule(); loadTrend() }, 2000)
  } finally {
    executing.value = false
  }
}

onMounted(async () => {
  const tplRes: any = await getQualityTemplates()
  templates.value = tplRes
  await Promise.all([loadRule(), loadTrend()])
})
</script>

<style scoped>
.content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.info-card, .config-card, .results-card, .trend-card {
  padding: 16px;
}
.config-json {
  background: var(--color-fill-2);
  border-radius: 6px;
  padding: 12px;
  font-size: 12px;
  overflow-x: auto;
  max-height: 200px;
}
h4 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 500;
}
.trend-bar {
  display: flex;
  gap: 4px;
  align-items: flex-end;
  height: 40px;
}
.trend-dot {
  width: 12px;
  height: 24px;
  border-radius: 3px;
  cursor: pointer;
}
.trend-dot.pass { background: var(--color-success-6, #00b42a); }
.trend-dot.fail { background: var(--color-danger-6, #f53f3f); }
.trend-dot.error { background: var(--color-warning-6, #ff7d00); }
</style>
