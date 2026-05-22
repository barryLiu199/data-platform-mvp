<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { createBackfill } from '../api'

const props = defineProps<{
  visible: boolean
  workflowId: number
  workflowName: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'success'): void
}>()

const submitting = ref(false)
const form = reactive({
  date_range: [] as string[],
  parallel: 1,
  has_dep: false,
})

const estimateCount = computed(() => {
  if (form.date_range?.length !== 2) return 0
  const a = new Date(form.date_range[0])
  const b = new Date(form.date_range[1])
  return Math.max(0, Math.floor((+b - +a) / 86400000) + 1)
})

watch(() => props.visible, (v) => {
  if (v) {
    form.date_range = []
    form.parallel = 1
    form.has_dep = false
  }
})

async function onOk() {
  if (form.date_range?.length !== 2) {
    Message.warning('请选择日期范围')
    return
  }
  submitting.value = true
  try {
    await createBackfill({
      workflow_id: props.workflowId,
      date_from: form.date_range[0],
      date_to: form.date_range[1],
      parallel: form.has_dep ? 1 : form.parallel,
      has_dep: form.has_dep ? 1 : 0,
    })
    Message.success(`已创建 ${estimateCount.value} 个补数实例`)
    emit('update:visible', false)
    emit('success')
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '创建失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <a-modal
    :visible="visible"
    title="补数 — 补充历史数据"
    :width="520"
    @cancel="emit('update:visible', false)"
    @ok="onOk"
    :ok-loading="submitting"
    ok-text="提交补数"
    unmount-on-close
  >
    <a-form :model="form" auto-label-width>
      <a-form-item label="工作流">
        <span class="wf-name">{{ workflowName }}</span>
      </a-form-item>
      <a-form-item field="date_range" label="日期范围" :rules="[{ required: true, message: '请选择日期范围' }]">
        <a-range-picker v-model="form.date_range" style="width: 100%" />
      </a-form-item>
      <a-form-item field="has_dep" label="日期依赖">
        <a-switch v-model="form.has_dep" />
        <span class="hint">
          {{ form.has_dep ? '串行：按日顺序，失败立即停止后续' : '并行：受并行度限制' }}
        </span>
      </a-form-item>
      <a-form-item field="parallel" label="并行度" :disabled="form.has_dep">
        <a-input-number v-model="form.parallel" :min="1" :max="20" :disabled="form.has_dep" style="width: 140px" />
        <span class="hint">同一时刻最多运行的实例数</span>
      </a-form-item>
      <a-form-item label="预计实例数" v-if="estimateCount > 0">
        <span class="preview">
          <b>{{ estimateCount }}</b> 个，每天一个，可在 <a-link href="/scheduler/history" target="_blank">运行实例</a-link> 查看进度
        </span>
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped>
.wf-name { font-weight: 600; color: var(--color-text-primary); }
.hint { margin-left: 8px; color: var(--color-text-tertiary); font-size: 12px; }
.preview { color: var(--color-text-secondary); font-size: 13px; }
.preview b { color: var(--color-primary); font-size: 16px; font-family: var(--font-family-mono); margin-right: 4px; }
</style>
