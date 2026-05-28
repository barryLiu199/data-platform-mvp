<template>
  <div class="page">
    <PageHeader title="数据质量" description="配置数据质量规则，检查数据完整性、准确性与一致性">
      <template #actions>
        <a-button @click="handleBatchExecute" :loading="batchLoading">
          <template #icon><icon-play-arrow /></template>
          批量检查
        </a-button>
        <a-button type="primary" @click="showCreate = true">
          <template #icon><icon-plus /></template>
          新建规则
        </a-button>
      </template>
    </PageHeader>

    <!-- Stats -->
    <div class="stats-row">
      <div class="stat-mini-card">
        <div class="stat-value">{{ stats.total_rules || 0 }}</div>
        <div class="stat-label">总规则数</div>
      </div>
      <div class="stat-mini-card">
        <div class="stat-value pass">{{ stats.today_pass || 0 }}</div>
        <div class="stat-label">今日通过</div>
      </div>
      <div class="stat-mini-card">
        <div class="stat-value fail">{{ stats.today_fail || 0 }}</div>
        <div class="stat-label">今日失败</div>
      </div>
      <div class="stat-mini-card">
        <div class="stat-value">{{ stats.pass_rate || 0 }}%</div>
        <div class="stat-label">通过率</div>
      </div>
    </div>

    <!-- Filters -->
    <div class="glass-card filter-card">
      <a-space>
        <a-select v-model="filters.template_code" placeholder="模板类型" allow-clear style="width: 150px" @change="loadRules">
          <a-option v-for="t in templates" :key="t.code" :value="t.code">{{ t.name }}</a-option>
        </a-select>
        <a-select v-model="filters.datasource_id" placeholder="数据源" allow-clear style="width: 150px" @change="loadRules">
          <a-option v-for="ds in datasources" :key="ds.id" :value="ds.id">{{ ds.name }}</a-option>
        </a-select>
        <a-select v-model="filters.status" placeholder="状态" allow-clear style="width: 120px" @change="loadRules">
          <a-option value="pass">通过</a-option>
          <a-option value="fail">失败</a-option>
          <a-option value="error">异常</a-option>
        </a-select>
        <a-input-search v-model="filters.keyword" placeholder="搜索规则名" style="width: 200px" @search="loadRules" allow-clear />
      </a-space>
    </div>

    <!-- Table -->
    <div class="glass-card table-card">
      <a-table :data="rules" :loading="loading" :bordered="false" :pagination="pagination" stripe @page-change="onPageChange">
        <template #columns>
          <a-table-column title="规则名称" :width="200">
            <template #cell="{ record }">
              <a-link @click="$router.push(`/data-quality/${record.id}`)">{{ record.name }}</a-link>
            </template>
          </a-table-column>
          <a-table-column title="模板" data-index="template_code" :width="120">
            <template #cell="{ record }">
              <a-tag size="small">{{ templateName(record.template_code) }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="数据源/表" :width="200">
            <template #cell="{ record }">
              <span>{{ record.datasource_name || '-' }}</span>
              <span v-if="record.table_name" class="text-muted"> / {{ record.table_name }}</span>
            </template>
          </a-table-column>
          <a-table-column title="严重级别" :width="100">
            <template #cell="{ record }">
              <a-tag :color="severityColor(record.severity)" size="small">{{ severityLabel(record.severity) }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="最近检查" :width="160">
            <template #cell="{ record }">
              <span v-if="record.last_check_time">{{ record.last_check_time.replace('T', ' ').slice(0, 16) }}</span>
              <span v-else class="text-muted">未检查</span>
            </template>
          </a-table-column>
          <a-table-column title="状态" :width="80">
            <template #cell="{ record }">
              <a-tag v-if="record.last_check_status === 'pass'" color="green" size="small">通过</a-tag>
              <a-tag v-else-if="record.last_check_status === 'fail'" color="red" size="small">失败</a-tag>
              <a-tag v-else-if="record.last_check_status === 'error'" color="orange" size="small">异常</a-tag>
              <span v-else class="text-muted">-</span>
            </template>
          </a-table-column>
          <a-table-column title="操作" :width="180" fixed="right">
            <template #cell="{ record }">
              <a-space>
                <a-button size="mini" type="text" @click="handleExecute(record)">
                  <template #icon><icon-play-arrow /></template>
                </a-button>
                <a-button size="mini" type="text" @click="handleToggle(record)">
                  <template #icon><component :is="record.enabled ? 'icon-pause' : 'icon-play-arrow'" /></template>
                </a-button>
                <a-button size="mini" type="text" @click="openEdit(record)">
                  <template #icon><icon-edit /></template>
                </a-button>
                <a-popconfirm content="确定删除此规则？" @ok="handleDelete(record)">
                  <a-button size="mini" type="text" status="danger">
                    <template #icon><icon-delete /></template>
                  </a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </div>

    <!-- Create/Edit Modal -->
    <a-modal v-model:visible="showCreate" :title="editingRule ? '编辑规则' : '新建规则'" :width="680" @ok="handleSave" :ok-loading="saving">
      <a-form :model="form" layout="vertical">
        <!-- Step 1: Template Selection (only for create) -->
        <div v-if="!editingRule && !form.template_code" class="template-grid">
          <div
            v-for="t in templates"
            :key="t.code"
            class="template-card"
            @click="selectTemplate(t)"
          >
            <div class="template-name">{{ t.name }}</div>
            <div class="template-desc">{{ t.description }}</div>
            <a-tag size="small" :color="categoryColor(t.category)">{{ t.category }}</a-tag>
          </div>
        </div>

        <!-- Step 2: Config Form -->
        <template v-if="form.template_code">
          <a-form-item v-if="!editingRule">
            <a-link @click="form.template_code = ''">
              <icon-left /> 重选模板
            </a-link>
            <a-tag style="margin-left: 8px">{{ templateName(form.template_code) }}</a-tag>
          </a-form-item>

          <a-form-item label="规则名称" required>
            <a-input v-model="form.name" placeholder="如：订单表主键唯一性" />
          </a-form-item>

          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item label="数据源">
                <a-select v-model="form.datasource_id" placeholder="选择数据源" allow-clear>
                  <a-option v-for="ds in datasources" :key="ds.id" :value="ds.id">{{ ds.name }}</a-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="表名">
                <a-input v-model="form.table_name" placeholder="表名" />
              </a-form-item>
            </a-col>
          </a-row>

          <!-- Dynamic config based on template -->
          <a-form-item v-if="needsField" label="字段名">
            <a-input v-model="form.config.field" placeholder="字段名" />
          </a-form-item>
          <a-form-item v-if="form.template_code === 'uniqueness'" label="检查字段（逗号分隔）">
            <a-input v-model="fieldsInput" placeholder="field1, field2" />
          </a-form-item>
          <a-form-item v-if="form.template_code === 'value_range'" label="值范围">
            <a-row :gutter="8">
              <a-col :span="12"><a-input-number v-model="form.config.min_value" placeholder="最小值" style="width:100%" /></a-col>
              <a-col :span="12"><a-input-number v-model="form.config.max_value" placeholder="最大值" style="width:100%" /></a-col>
            </a-row>
          </a-form-item>
          <a-form-item v-if="form.template_code === 'regex_match'" label="正则表达式">
            <a-input v-model="form.config.pattern" placeholder="^1[3-9]\d{9}$" />
          </a-form-item>
          <a-form-item v-if="form.template_code === 'null_rate' || form.template_code === 'row_count'" label="阈值(%)">
            <a-input-number v-model="form.config.threshold_pct" :min="0" :max="100" style="width: 120px" />
          </a-form-item>
          <a-form-item v-if="form.template_code === 'timeliness'" label="日期字段">
            <a-input v-model="form.config.date_field" placeholder="trade_date" />
          </a-form-item>
          <a-form-item v-if="form.template_code === 'dict_ref'" label="字典表配置">
            <a-row :gutter="8">
              <a-col :span="8"><a-input v-model="form.config.dict_table" placeholder="字典表" /></a-col>
              <a-col :span="8"><a-input v-model="form.config.dict_field" placeholder="字典字段" /></a-col>
            </a-row>
          </a-form-item>
          <a-form-item v-if="form.template_code === 'custom_sql'" label="SQL">
            <a-textarea v-model="form.config.sql" :auto-size="{ minRows: 3, maxRows: 8 }" placeholder="SELECT COUNT(*) FROM ..." />
          </a-form-item>
          <a-form-item v-if="form.template_code === 'custom_sql'" label="判定条件">
            <a-row :gutter="8">
              <a-col :span="8">
                <a-select v-model="form.config.operator">
                  <a-option value="=">=</a-option>
                  <a-option value="!=">!=</a-option>
                  <a-option value=">">></a-option>
                  <a-option value=">=">>>=</a-option>
                  <a-option value="<"><</a-option>
                  <a-option value="<="><=</a-option>
                </a-select>
              </a-col>
              <a-col :span="8"><a-input-number v-model="form.config.threshold" placeholder="阈值" style="width:100%" /></a-col>
            </a-row>
          </a-form-item>

          <a-divider />

          <a-row :gutter="16">
            <a-col :span="8">
              <a-form-item label="严重级别">
                <a-select v-model="form.severity">
                  <a-option value="info">信息</a-option>
                  <a-option value="warning">警告</a-option>
                  <a-option value="error">严重</a-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="触发方式">
                <a-select v-model="form.trigger_type">
                  <a-option value="manual">手动</a-option>
                  <a-option value="workflow">工作流触发</a-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="通知">
                <a-switch v-model="form.notify_enabled" />
              </a-form-item>
            </a-col>
          </a-row>
        </template>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import PageHeader from '../components/PageHeader.vue'
import {
  getQualityTemplates, getQualityRules, createQualityRule, updateQualityRule,
  deleteQualityRule, toggleQualityRule, executeQualityRule, batchExecuteQuality,
  getQualityStats, getDatasources,
} from '../api'

const loading = ref(false)
const batchLoading = ref(false)
const saving = ref(false)
const showCreate = ref(false)
const editingRule = ref<any>(null)

const rules = ref<any[]>([])
const templates = ref<any[]>([])
const datasources = ref<any[]>([])
const stats = ref<any>({})

const filters = reactive({
  template_code: undefined as string | undefined,
  datasource_id: undefined as number | undefined,
  status: undefined as string | undefined,
  keyword: '',
})

const pagination = reactive({ current: 1, pageSize: 20, total: 0 })

const form = reactive<any>({
  name: '',
  template_code: '',
  datasource_id: undefined,
  table_name: '',
  column_name: '',
  config: {},
  severity: 'warning',
  trigger_type: 'manual',
  trigger_workflow_id: undefined,
  notify_enabled: false,
  notify_channel_ids: [],
})

const fieldsInput = ref('')

const needsField = computed(() =>
  ['not_null', 'null_rate', 'value_range', 'regex_match', 'dict_ref'].includes(form.template_code)
)

function templateName(code: string) {
  return templates.value.find((t: any) => t.code === code)?.name || code
}

function severityColor(s: string) {
  return s === 'error' ? 'red' : s === 'warning' ? 'orange' : 'blue'
}
function severityLabel(s: string) {
  return s === 'error' ? '严重' : s === 'warning' ? '警告' : '信息'
}
function categoryColor(c: string) {
  const m: Record<string, string> = { accuracy: 'blue', completeness: 'green', timeliness: 'orange', consistency: 'purple' }
  return m[c] || 'gray'
}

function selectTemplate(t: any) {
  form.template_code = t.code
  form.config = {}
}

function openEdit(record: any) {
  editingRule.value = record
  Object.assign(form, {
    name: record.name,
    template_code: record.template_code,
    datasource_id: record.datasource_id,
    table_name: record.table_name,
    config: { ...(record.config || {}) },
    severity: record.severity,
    trigger_type: record.trigger_type,
    notify_enabled: record.notify_enabled,
  })
  if (record.config?.fields) {
    fieldsInput.value = record.config.fields.join(', ')
  }
  showCreate.value = true
}

function resetForm() {
  Object.assign(form, {
    name: '', template_code: '', datasource_id: undefined,
    table_name: '', column_name: '', config: {},
    severity: 'warning', trigger_type: 'manual',
    trigger_workflow_id: undefined, notify_enabled: false, notify_channel_ids: [],
  })
  fieldsInput.value = ''
  editingRule.value = null
}

async function loadRules() {
  loading.value = true
  try {
    const { data } = await getQualityRules({
      page: pagination.current,
      page_size: pagination.pageSize,
      ...filters,
    })
    rules.value = data.items
    pagination.total = data.total
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  const { data } = await getQualityStats()
  stats.value = data
}

function onPageChange(page: number) {
  pagination.current = page
  loadRules()
}

async function handleSave() {
  if (!form.name || !form.template_code) {
    Message.warning('请填写规则名称并选择模板')
    return
  }
  // Sync fieldsInput to config for uniqueness template
  if (form.template_code === 'uniqueness' && fieldsInput.value) {
    form.config.fields = fieldsInput.value.split(',').map((s: string) => s.trim()).filter(Boolean)
  }

  saving.value = true
  try {
    if (editingRule.value) {
      await updateQualityRule(editingRule.value.id, form)
      Message.success('更新成功')
    } else {
      await createQualityRule(form)
      Message.success('创建成功')
    }
    showCreate.value = false
    resetForm()
    loadRules()
    loadStats()
  } finally {
    saving.value = false
  }
}

async function handleDelete(record: any) {
  await deleteQualityRule(record.id)
  Message.success('删除成功')
  loadRules()
  loadStats()
}

async function handleToggle(record: any) {
  const { data } = await toggleQualityRule(record.id)
  record.enabled = data.enabled
  Message.success(data.enabled ? '已启用' : '已禁用')
}

async function handleExecute(record: any) {
  await executeQualityRule(record.id)
  Message.success('已提交执行')
}

async function handleBatchExecute() {
  batchLoading.value = true
  try {
    await batchExecuteQuality()
    Message.success('已提交批量检查')
  } finally {
    batchLoading.value = false
  }
}

onMounted(async () => {
  const [tplRes, dsRes] = await Promise.all([
    getQualityTemplates(),
    getDatasources(),
  ])
  templates.value = tplRes.data
  datasources.value = dsRes.data
  await Promise.all([loadRules(), loadStats()])
})
</script>

<style scoped>
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.stat-mini-card {
  background: var(--color-bg-2);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  border: 1px solid var(--color-border);
}
.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--color-text-1);
}
.stat-value.pass { color: var(--color-success-6, #00b42a); }
.stat-value.fail { color: var(--color-danger-6, #f53f3f); }
.stat-label {
  font-size: 12px;
  color: var(--color-text-3);
  margin-top: 4px;
}
.filter-card {
  padding: 12px 16px;
  margin-bottom: 16px;
}
.table-card {
  padding: 16px;
}
.template-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.template-card {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 12px;
  cursor: pointer;
  transition: border-color 0.2s;
}
.template-card:hover {
  border-color: var(--color-primary, #2563eb);
}
.template-name {
  font-weight: 500;
  margin-bottom: 4px;
}
.template-desc {
  font-size: 12px;
  color: var(--color-text-3);
  margin-bottom: 8px;
}
.text-muted {
  color: var(--color-text-3);
}
</style>
