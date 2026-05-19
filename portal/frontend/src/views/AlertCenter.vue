<template>
  <div class="page">
    <PageHeader title="监控规则" description="配置告警规则，工作流异常时自动通知到飞书或邮箱">
      <template #actions>
        <a-button type="primary" @click="openCreate">
          <template #icon><icon-plus /></template>
          新建规则
        </a-button>
      </template>
    </PageHeader>

    <div class="glass-card table-card">
      <a-table :data="rules" :loading="loading" :bordered="false" :pagination="false" stripe>
        <template #columns>
          <a-table-column title="规则名称" data-index="name" :width="180" />
          <a-table-column title="监控对象" :width="160">
            <template #cell="{ record }">
              <span v-if="record.target_type === 'all'" class="text-muted">所有工作流</span>
              <span v-else>{{ record.target_name || `工作流#${record.target_id}` }}</span>
            </template>
          </a-table-column>
          <a-table-column title="触发条件" :width="160">
            <template #cell="{ record }">
              <a-tag :color="triggerColor(record.trigger_type)" size="small">{{ triggerLabel(record) }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="通知方式" :width="120">
            <template #cell="{ record }">
              <span class="notify-badge">
                <span class="notify-icon">{{ record.notify_type === 'feishu_webhook' ? '🔔' : '📧' }}</span>
                {{ record.notify_type === 'feishu_webhook' ? '飞书' : '邮件' }}
              </span>
            </template>
          </a-table-column>
          <a-table-column title="状态" :width="80">
            <template #cell="{ record }">
              <a-switch :model-value="record.enabled" size="small" @change="handleToggle(record)" />
            </template>
          </a-table-column>
          <a-table-column title="操作" :width="160">
            <template #cell="{ record }">
              <a-space :size="4">
                <a-button type="text" size="mini" @click="openEdit(record)">编辑</a-button>
                <a-button type="text" size="mini" @click="handleTest(record)">测试</a-button>
                <a-button type="text" size="mini" status="danger" @click="handleDelete(record)">删除</a-button>
              </a-space>
            </template>
          </a-table-column>
        </template>
        <template #empty>
          <EmptyState description="暂无监控规则">
            <p class="text-muted">点击「新建规则」配置工作流异常告警</p>
          </EmptyState>
        </template>
      </a-table>
    </div>

    <!-- 新建/编辑模态框 -->
    <a-modal v-model:visible="modalVisible" :title="editingId ? '编辑规则' : '新建规则'" :width="560" @ok="handleSave" :unmount-on-close="true">
      <a-form :model="form" layout="vertical">
        <a-form-item label="规则名称" required>
          <a-input v-model="form.name" placeholder="例如：ODS同步失败告警" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="监控对象">
              <a-select v-model="form.target_type">
                <a-option value="all">所有工作流</a-option>
                <a-option value="workflow">指定工作流</a-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12" v-if="form.target_type === 'workflow'">
            <a-form-item label="选择工作流">
              <a-select v-model="form.target_id" placeholder="选择" allow-search>
                <a-option v-for="w in workflows" :key="w.id" :value="w.id">{{ w.name }}</a-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="触发条件">
              <a-select v-model="form.trigger_type">
                <a-option value="failure">运行失败</a-option>
                <a-option value="timeout">运行超时</a-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12" v-if="form.trigger_type === 'timeout'">
            <a-form-item label="超时阈值（秒）">
              <a-input-number v-model="form.trigger_value" :min="60" :step="60" placeholder="600" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="通知方式">
              <a-select v-model="form.notify_type">
                <a-option value="feishu_webhook">飞书机器人</a-option>
                <a-option value="email">邮件</a-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="form.notify_type === 'feishu_webhook' ? 'Webhook URL' : '邮箱地址'">
              <a-input v-model="notifyValue" :placeholder="form.notify_type === 'feishu_webhook' ? 'https://open.feishu.cn/open-apis/bot/v2/hook/...' : 'alert@example.com'" />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { IconPlus } from '@arco-design/web-vue/es/icon'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import {
  getAlertRules, createAlertRule, updateAlertRule, deleteAlertRule,
  toggleAlertRule, testAlertNotify, getWorkflows,
} from '../api'

interface Rule {
  id: number
  name: string
  target_type: string
  target_id?: number
  target_name?: string
  trigger_type: string
  trigger_value?: number
  notify_type: string
  notify_config: any
  enabled: boolean
}

const loading = ref(false)
const rules = ref<Rule[]>([])
const workflows = ref<any[]>([])
const modalVisible = ref(false)
const editingId = ref<number | null>(null)
const notifyValue = ref('')

const form = ref({
  name: '',
  target_type: 'all',
  target_id: undefined as number | undefined,
  trigger_type: 'failure',
  trigger_value: 600,
  notify_type: 'feishu_webhook',
})

function triggerColor(t: string) {
  return ({ failure: 'red', timeout: 'orange', consecutive_failure: 'purple' } as any)[t] || 'gray'
}
function triggerLabel(r: Rule) {
  if (r.trigger_type === 'failure') return '运行失败'
  if (r.trigger_type === 'timeout') return `超时 > ${r.trigger_value || 0}s`
  if (r.trigger_type === 'consecutive_failure') return `连续失败 ${r.trigger_value} 次`
  return r.trigger_type
}

async function loadData() {
  loading.value = true
  try {
    const res: any = await getAlertRules()
    rules.value = res?.items || []
  } catch { rules.value = [] }
  loading.value = false
}

async function loadWorkflows() {
  try {
    const res: any = await getWorkflows({ page: 1, page_size: 200 })
    workflows.value = res?.items || []
  } catch {}
}

function openCreate() {
  editingId.value = null
  form.value = { name: '', target_type: 'all', target_id: undefined, trigger_type: 'failure', trigger_value: 600, notify_type: 'feishu_webhook' }
  notifyValue.value = ''
  modalVisible.value = true
}

function openEdit(r: Rule) {
  editingId.value = r.id
  form.value = {
    name: r.name,
    target_type: r.target_type,
    target_id: r.target_id,
    trigger_type: r.trigger_type,
    trigger_value: r.trigger_value || 600,
    notify_type: r.notify_type,
  }
  const cfg = r.notify_config || {}
  notifyValue.value = cfg.webhook_url || cfg.email || ''
  modalVisible.value = true
}

async function handleSave() {
  if (!form.value.name.trim()) { Message.warning('请填写规则名称'); return }
  if (!notifyValue.value.trim()) { Message.warning('请填写通知地址'); return }

  const notify_config = form.value.notify_type === 'feishu_webhook'
    ? { webhook_url: notifyValue.value.trim() }
    : { email: notifyValue.value.trim() }

  const payload = { ...form.value, notify_config }
  try {
    if (editingId.value) {
      await updateAlertRule(editingId.value, payload)
      Message.success('已更新')
    } else {
      await createAlertRule(payload)
      Message.success('已创建')
    }
    modalVisible.value = false
    loadData()
  } catch {}
}

async function handleToggle(r: Rule) {
  try {
    await toggleAlertRule(r.id)
    loadData()
  } catch {}
}

async function handleTest(r: Rule) {
  try {
    await testAlertNotify({ notify_type: r.notify_type, notify_config: r.notify_config })
    Message.success('测试通知已发送，请检查接收端')
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '发送失败')
  }
}

function handleDelete(r: Rule) {
  Modal.confirm({
    title: '删除规则',
    content: `确认删除「${r.name}」?`,
    onOk: async () => {
      try { await deleteAlertRule(r.id); Message.success('已删除'); loadData() } catch {}
    },
  })
}

onMounted(() => { loadData(); loadWorkflows() })
</script>

<style scoped>
.page { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.table-card { padding: 0; overflow: auto; }
.text-muted { color: var(--color-text-tertiary); }

.notify-badge { display: inline-flex; align-items: center; gap: 4px; font-size: var(--font-size-sm); }
.notify-icon { font-size: var(--font-size-base); }
</style>
