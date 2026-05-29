<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { Message } from '@arco-design/web-vue'
import {
  getDatasources, getMetadataTables, getMetadataColumns,
  createManualColumnLineage,
} from '../../api'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'created'): void
}>()

interface DSOption { id: number; name: string }

const datasources = ref<DSOption[]>([])
const srcDsId = ref<number | null>(null)
const tgtDsId = ref<number | null>(null)
const srcTables = ref<string[]>([])
const tgtTables = ref<string[]>([])
const srcCols = ref<string[]>([])
const tgtCols = ref<string[]>([])

const form = ref({
  source_table: '',
  source_column: '',
  target_table: '',
  target_column: '',
  transform_type: 'identity' as 'identity' | 'expression' | 'aggregate' | 'join',
  transform_expr: '',
})

const submitting = ref(false)

const canSubmit = computed(() => Boolean(
  form.value.source_table && form.value.source_column &&
  form.value.target_table && form.value.target_column
))

async function loadDatasources() {
  try {
    const res: any = await getDatasources({ page: 1, page_size: 200 })
    datasources.value = (res?.items || res || []).map((d: any) => ({ id: d.id, name: d.name }))
  } catch { datasources.value = [] }
}

async function loadSrcTables() {
  if (!srcDsId.value) { srcTables.value = []; return }
  try {
    const res: any = await getMetadataTables(srcDsId.value, '', 500)
    srcTables.value = (res?.items || res || []).map((t: any) => t.name || t)
  } catch { srcTables.value = [] }
}

async function loadTgtTables() {
  if (!tgtDsId.value) { tgtTables.value = []; return }
  try {
    const res: any = await getMetadataTables(tgtDsId.value, '', 500)
    tgtTables.value = (res?.items || res || []).map((t: any) => t.name || t)
  } catch { tgtTables.value = [] }
}

async function loadSrcCols() {
  if (!srcDsId.value || !form.value.source_table) { srcCols.value = []; return }
  try {
    const res: any = await getMetadataColumns(srcDsId.value, form.value.source_table)
    srcCols.value = (res?.items || res || []).map((c: any) => c.name || c.column_name || c.COLUMN_NAME).filter(Boolean)
  } catch { srcCols.value = [] }
}

async function loadTgtCols() {
  if (!tgtDsId.value || !form.value.target_table) { tgtCols.value = []; return }
  try {
    const res: any = await getMetadataColumns(tgtDsId.value, form.value.target_table)
    tgtCols.value = (res?.items || res || []).map((c: any) => c.name || c.column_name || c.COLUMN_NAME).filter(Boolean)
  } catch { tgtCols.value = [] }
}

watch(() => props.visible, (v) => {
  if (v) {
    loadDatasources()
    // 重置表单
    srcDsId.value = null
    tgtDsId.value = null
    form.value = {
      source_table: '', source_column: '',
      target_table: '', target_column: '',
      transform_type: 'identity', transform_expr: '',
    }
  }
})

watch(srcDsId, loadSrcTables)
watch(tgtDsId, loadTgtTables)
watch(() => form.value.source_table, loadSrcCols)
watch(() => form.value.target_table, loadTgtCols)

async function onSubmit() {
  if (!canSubmit.value) {
    Message.warning('请填写完整源/目标 表+字段')
    return
  }
  submitting.value = true
  try {
    await createManualColumnLineage({
      source_table: form.value.source_table,
      source_column: form.value.source_column,
      target_table: form.value.target_table,
      target_column: form.value.target_column,
      transform_type: form.value.transform_type,
      transform_expr: form.value.transform_expr || null,
      source_ds_id: srcDsId.value,
      target_ds_id: tgtDsId.value,
    })
    emit('created')
  } catch { /* 拦截器提示 */ }
  submitting.value = false
}

function onCancel() { emit('update:visible', false) }
</script>

<template>
  <a-modal
    :visible="visible"
    title="手工补登字段血缘"
    width="640"
    :ok-loading="submitting"
    :ok-button-props="{ disabled: !canSubmit }"
    @ok="onSubmit"
    @cancel="onCancel"
  >
    <a-form :model="form" layout="vertical">
      <div class="grid">
        <a-form-item label="源数据源">
          <a-select v-model="srcDsId" placeholder="选择源数据源" allow-search>
            <a-option v-for="d in datasources" :key="d.id" :value="d.id">{{ d.name }}</a-option>
          </a-select>
        </a-form-item>
        <a-form-item label="目标数据源">
          <a-select v-model="tgtDsId" placeholder="选择目标数据源" allow-search>
            <a-option v-for="d in datasources" :key="d.id" :value="d.id">{{ d.name }}</a-option>
          </a-select>
        </a-form-item>

        <a-form-item label="源表">
          <a-select v-model="form.source_table" placeholder="选择或输入源表" allow-search allow-create>
            <a-option v-for="t in srcTables" :key="t" :value="t">{{ t }}</a-option>
          </a-select>
        </a-form-item>
        <a-form-item label="目标表">
          <a-select v-model="form.target_table" placeholder="选择或输入目标表" allow-search allow-create>
            <a-option v-for="t in tgtTables" :key="t" :value="t">{{ t }}</a-option>
          </a-select>
        </a-form-item>

        <a-form-item label="源字段">
          <a-select v-model="form.source_column" placeholder="选择或输入源字段" allow-search allow-create>
            <a-option v-for="c in srcCols" :key="c" :value="c">{{ c }}</a-option>
          </a-select>
        </a-form-item>
        <a-form-item label="目标字段">
          <a-select v-model="form.target_column" placeholder="选择或输入目标字段" allow-search allow-create>
            <a-option v-for="c in tgtCols" :key="c" :value="c">{{ c }}</a-option>
          </a-select>
        </a-form-item>
      </div>

      <a-form-item label="转换类型">
        <a-radio-group v-model="form.transform_type">
          <a-radio value="identity">直传</a-radio>
          <a-radio value="expression">表达式</a-radio>
          <a-radio value="aggregate">聚合</a-radio>
          <a-radio value="join">关联</a-radio>
        </a-radio-group>
      </a-form-item>

      <a-form-item v-if="form.transform_type !== 'identity'" label="转换表达式（可选）">
        <a-input v-model="form.transform_expr" placeholder="如 SUM(amount) 或 a.x + b.y" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 var(--space-4);
}
</style>
