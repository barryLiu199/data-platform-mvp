<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { complementDSWorkflow } from '../api'

const props = defineProps<{
  visible: boolean
  workflowName: string
  dsProcessCode: number
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'success'): void
}>()

const dateRange = ref<string[]>([])
const submitting = ref(false)

// 计算天数预览
const dayCount = computed(() => {
  if (dateRange.value.length !== 2) return 0
  const start = new Date(dateRange.value[0])
  const end = new Date(dateRange.value[1])
  return Math.max(1, Math.round((end.getTime() - start.getTime()) / 86400000) + 1)
})

watch(() => props.visible, (v) => {
  if (v) {
    dateRange.value = []
  }
})

async function handleSubmit() {
  if (dateRange.value.length !== 2) {
    Message.warning('请选择日期范围')
    return
  }
  const startDate = dateRange.value[0] + ' 00:00:00'
  const endDate = dateRange.value[1] + ' 00:00:00'

  submitting.value = true
  try {
    await complementDSWorkflow(props.dsProcessCode, startDate, endDate)
    Message.success(`已提交补数，共 ${dayCount.value} 天`)
    emit('update:visible', false)
    emit('success')
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '补数失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <a-modal
    :visible="visible"
    title="补数 — 补充历史数据"
    :width="480"
    @cancel="emit('update:visible', false)"
    @ok="handleSubmit"
    :ok-loading="submitting"
    ok-text="提交补数"
    unmount-on-close
  >
    <div class="complement-form">
      <div class="form-item">
        <div class="form-label">工作流</div>
        <div class="form-value wf-name">{{ workflowName }}</div>
      </div>

      <div class="form-item">
        <div class="form-label">日期范围</div>
        <a-range-picker
          v-model="dateRange"
          style="width: 100%;"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
        />
      </div>

      <div class="form-item" v-if="dayCount > 0">
        <div class="form-label">预览</div>
        <div class="preview-box">
          <span class="preview-count">{{ dayCount }}</span>
          <span class="preview-text">
            天的实例将按<strong>串行</strong>顺序依次执行
          </span>
        </div>
      </div>

      <div class="form-hint">
        补数会为选定日期范围内的每一天创建一个工作流实例，按顺序执行。
        适用于重跑历史数据或填补缺失的调度。
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.complement-form { display: flex; flex-direction: column; gap: 16px; }
.form-item { display: flex; flex-direction: column; gap: 6px; }
.form-label { font-size: 13px; font-weight: 500; color: var(--color-text-secondary); }
.form-value { font-size: 14px; color: var(--color-text-primary); }
.wf-name { font-weight: 600; }
.preview-box {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; background: var(--color-primary-light); border-radius: var(--radius-md);
}
.preview-count {
  font-size: 24px; font-weight: 700; color: var(--color-primary);
  font-family: var(--font-family-mono);
}
.preview-text { font-size: 13px; color: var(--color-text-secondary); }
.form-hint {
  font-size: 12px; color: var(--color-text-tertiary); line-height: 1.6;
  padding: 10px 12px; background: var(--color-bg-elevated); border-radius: var(--radius-md);
}
</style>
