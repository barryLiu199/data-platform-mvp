<script setup lang="ts">
import { ref, computed } from 'vue'
import { Modal } from '@arco-design/web-vue'

export interface NodeConfig {
  skip: boolean
  fail_strategy: 'end' | 'skip'
  retry_times: number
  retry_interval: number
  timeout: number
  priority: string
}

const visible = ref(false)
const nodeId = ref<string | null>(null)
const nodeName = ref('')
const nodeType = ref('')

const form = ref<NodeConfig>({
  skip: false,
  fail_strategy: 'end',
  retry_times: 0,
  retry_interval: 1,
  timeout: 0,
  priority: 'MEDIUM',
})

const emit = defineEmits<{
  (e: 'save', id: string, cfg: NodeConfig): void
  (e: 'delete', id: string): void
}>()

const PRIORITY_OPTIONS = [
  { value: 'HIGHEST', label: '最高' },
  { value: 'HIGH', label: '高' },
  { value: 'MEDIUM', label: '中（默认）' },
  { value: 'LOW', label: '低' },
  { value: 'LOWEST', label: '最低' },
]

// 失败跳过时节点退出码恒为 0，重试不会触发，二者互斥
const retryDisabled = computed(() => form.value.fail_strategy === 'skip')

function open(id: string, data: any) {
  nodeId.value = id
  nodeName.value = data.label || ''
  nodeType.value = data.type || 'sql'
  form.value = {
    skip: data.skip || false,
    fail_strategy: data.fail_strategy === 'skip' ? 'skip' : 'end',
    retry_times: Number(data.retry_times) || 0,
    retry_interval: Number(data.retry_interval) || 1,
    timeout: Number(data.timeout) || 0,
    priority: data.priority || 'MEDIUM',
  }
  visible.value = true
}

function handleOk() {
  if (!nodeId.value) return
  const cfg = { ...form.value }
  if (cfg.fail_strategy === 'skip') {
    cfg.retry_times = 0
  }
  emit('save', nodeId.value, cfg)
  visible.value = false
}

function handleDelete() {
  if (!nodeId.value) return
  const id = nodeId.value
  Modal.warning({
    title: '删除节点',
    content: `确定删除节点「${nodeName.value}」吗？相关连线将一并删除。`,
    hideCancel: false,
    okText: '删除',
    okButtonProps: { status: 'danger' },
    onOk: () => {
      emit('delete', id)
      visible.value = false
    },
  })
}

defineExpose({ open })
</script>

<template>
  <a-modal v-model:visible="visible" :width="520" title-align="start" @ok="handleOk">
    <template #title>节点配置 — {{ nodeName }}</template>
    <a-form :model="form" layout="vertical">
      <a-form-item label="跳过节点">
        <a-switch v-model="form.skip" />
        <span class="cfg-hint">跳过后该节点不参与调度执行</span>
      </a-form-item>

      <a-form-item label="失败策略">
        <a-radio-group v-model="form.fail_strategy">
          <a-radio value="end">失败终止 — 节点失败后终止后续流程</a-radio>
          <a-radio value="skip">失败跳过 — 节点失败仅记录日志，继续执行后续节点</a-radio>
        </a-radio-group>
        <div v-if="form.fail_strategy === 'skip'" class="cfg-hint cfg-hint--warn">
          失败跳过模式下节点总是视为成功，失败重试将不生效
        </div>
      </a-form-item>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="失败重试次数">
            <a-input-number v-model="form.retry_times" :min="0" :max="10" :disabled="retryDisabled" style="width: 100%">
              <template #suffix>次</template>
            </a-input-number>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="重试间隔">
            <a-input-number v-model="form.retry_interval" :min="1" :max="60" :disabled="retryDisabled || form.retry_times === 0" style="width: 100%">
              <template #suffix>分钟</template>
            </a-input-number>
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="超时时间（0 表示不限制）">
            <a-input-number v-model="form.timeout" :min="0" :max="1440" style="width: 100%">
              <template #suffix>分钟</template>
            </a-input-number>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="任务优先级">
            <a-select v-model="form.priority">
              <a-option v-for="p in PRIORITY_OPTIONS" :key="p.value" :value="p.value">{{ p.label }}</a-option>
            </a-select>
          </a-form-item>
        </a-col>
      </a-row>
    </a-form>

    <template #footer>
      <div class="cfg-footer">
        <a-button status="danger" @click="handleDelete">删除节点</a-button>
        <div class="cfg-footer__right">
          <a-button @click="visible = false">取消</a-button>
          <a-button type="primary" @click="handleOk">确定</a-button>
        </div>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
.cfg-hint { margin-left: 12px; font-size: 12px; color: var(--color-text-3, #86909c); }
.cfg-hint--warn { margin-left: 0; margin-top: 4px; color: var(--color-warning, #f59e0b); }
.cfg-footer { display: flex; justify-content: space-between; align-items: center; width: 100%; }
.cfg-footer__right { display: flex; gap: 8px; }
</style>
