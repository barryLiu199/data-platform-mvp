<template>
  <div class="admin-page">
    <PageHeader title="通知配置" description="管理告警通知渠道，供监控规则与数据质量规则引用">
      <template #actions>
        <a-button type="primary" @click="openCreate">
          <template #icon><icon-plus /></template>
          新建渠道
        </a-button>
      </template>
    </PageHeader>

    <div class="glass-card" style="padding: 16px">
      <a-table :data="channels" :loading="loading" :pagination="false" row-key="id">
        <template #columns>
          <a-table-column title="名称" data-index="name" />
          <a-table-column title="类型">
            <template #cell="{ record }">
              <a-tag :color="typeMeta[record.type]?.color || 'gray'">
                {{ typeMeta[record.type]?.label || record.type }}
              </a-tag>
            </template>
          </a-table-column>
          <a-table-column title="状态">
            <template #cell="{ record }">
              <a-badge :status="record.enabled ? 'success' : 'normal'" :text="record.enabled ? '启用' : '停用'" />
            </template>
          </a-table-column>
          <a-table-column title="更新时间" data-index="updated_at" />
          <a-table-column title="操作" :width="220">
            <template #cell="{ record }">
              <a-space>
                <a-button size="mini" :loading="testing === record.id" @click="testChannel(record)">测试</a-button>
                <a-button size="mini" @click="openEdit(record)">编辑</a-button>
                <a-popconfirm content="确认删除该渠道？引用它的规则将不再发送通知。" @ok="removeChannel(record)">
                  <a-button size="mini" status="danger">删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table-column>
        </template>
        <template #empty>
          <EmptyState description="还没有通知渠道，点击右上角新建" />
        </template>
      </a-table>
    </div>

    <a-modal
      v-model:visible="modalVisible"
      :title="editingId ? '编辑渠道' : '新建渠道'"
      :ok-loading="saving"
      @ok="save"
      @cancel="modalVisible = false"
    >
      <a-form :model="form" layout="vertical">
        <a-form-item label="渠道名称" required>
          <a-input v-model="form.name" placeholder="如：数据组飞书群" />
        </a-form-item>
        <a-form-item label="渠道类型" required>
          <a-select v-model="form.type" :disabled="!!editingId" placeholder="选择类型">
            <a-option v-for="(m, t) in typeMeta" :key="t" :value="t">{{ m.label }}</a-option>
          </a-select>
        </a-form-item>

        <template v-if="isWebhook">
          <a-form-item label="Webhook URL" required>
            <a-input v-model="form.config.webhook_url" placeholder="https://..." />
          </a-form-item>
          <a-form-item v-if="form.type === 'dingtalk_webhook'" label="加签密钥（可选）">
            <a-input-password v-model="form.config.secret" placeholder="钉钉机器人安全设置中的加签密钥" />
          </a-form-item>
        </template>

        <template v-if="form.type === 'email'">
          <a-form-item label="收件邮箱" required>
            <a-input v-model="form.config.email" placeholder="alert@example.com" />
          </a-form-item>
          <a-collapse :bordered="false">
            <a-collapse-item header="SMTP 设置（留空使用服务端默认配置）" key="smtp">
              <a-form-item label="SMTP 服务器">
                <a-input v-model="form.config.host" placeholder="smtp.163.com" />
              </a-form-item>
              <a-form-item label="端口">
                <a-input-number v-model="form.config.port" :default-value="465" />
              </a-form-item>
              <a-form-item label="发件账号">
                <a-input v-model="form.config.user" />
              </a-form-item>
              <a-form-item label="发件密码/授权码">
                <a-input-password v-model="form.config.password" />
              </a-form-item>
            </a-collapse-item>
          </a-collapse>
        </template>

        <a-form-item label="启用">
          <a-switch v-model="form.enabled" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconPlus } from '@arco-design/web-vue/es/icon'
import {
  adminListChannels, adminCreateChannel, adminUpdateChannel,
  adminDeleteChannel, adminTestChannel,
} from '../../api'
import PageHeader from '../../components/PageHeader.vue'
import EmptyState from '../../components/EmptyState.vue'

const typeMeta: Record<string, { label: string; color: string }> = {
  feishu_webhook: { label: '飞书机器人', color: 'arcoblue' },
  dingtalk_webhook: { label: '钉钉机器人', color: 'blue' },
  wecom_webhook: { label: '企微机器人', color: 'green' },
  email: { label: '邮件', color: 'orange' },
}

const channels = ref<any[]>([])
const loading = ref(false)
const testing = ref<number | null>(null)
const saving = ref(false)
const modalVisible = ref(false)
const editingId = ref<number | null>(null)

const emptyForm = () => ({
  name: '',
  type: 'feishu_webhook',
  enabled: true,
  config: { webhook_url: '', secret: '', email: '', host: '', port: 465, user: '', password: '' } as any,
})
const form = reactive(emptyForm())

const isWebhook = computed(() => form.type.endsWith('_webhook'))

async function load() {
  loading.value = true
  try {
    const res: any = await adminListChannels()
    channels.value = res || []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, emptyForm())
  modalVisible.value = true
}

function openEdit(record: any) {
  editingId.value = record.id
  Object.assign(form, emptyForm())
  form.name = record.name
  form.type = record.type
  form.enabled = record.enabled
  // 后端返回的 config 已脱敏（敏感字段为 ***），不回填密钥类字段
  const cfg = record.config || {}
  for (const k of Object.keys(form.config)) {
    if (cfg[k] !== undefined && cfg[k] !== '***') form.config[k] = cfg[k]
  }
  modalVisible.value = true
}

function buildConfig(): any {
  if (isWebhook.value) {
    const c: any = { webhook_url: form.config.webhook_url }
    if (form.type === 'dingtalk_webhook' && form.config.secret) c.secret = form.config.secret
    return c
  }
  const c: any = { email: form.config.email }
  if (form.config.host) {
    c.host = form.config.host
    c.port = form.config.port || 465
    c.user = form.config.user
    if (form.config.password) c.password = form.config.password
    c.use_ssl = true
  }
  return c
}

async function save() {
  if (!form.name.trim()) return Message.warning('请填写渠道名称')
  if (isWebhook.value && !form.config.webhook_url) return Message.warning('请填写 Webhook URL')
  if (form.type === 'email' && !form.config.email) return Message.warning('请填写收件邮箱')

  saving.value = true
  try {
    const payload = { name: form.name, type: form.type, enabled: form.enabled, config: buildConfig() }
    if (editingId.value) {
      await adminUpdateChannel(editingId.value, payload)
      Message.success('已更新')
    } else {
      await adminCreateChannel(payload)
      Message.success('已创建')
    }
    modalVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function testChannel(record: any) {
  testing.value = record.id
  try {
    await adminTestChannel(record.id)
    Message.success(`渠道「${record.name}」测试消息已发送`)
  } catch {
    Message.error('发送失败，请检查渠道配置')
  } finally {
    testing.value = null
  }
}

async function removeChannel(record: any) {
  await adminDeleteChannel(record.id)
  Message.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.admin-page { padding: 0; }
</style>
