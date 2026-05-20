<template>
  <a-modal v-model:visible="innerVisible" title="导入" :width="620" @cancel="reset">
    <!-- Step indicator -->
    <a-steps :current="step" size="small" style="margin-bottom: 20px">
      <a-step title="上传文件" />
      <a-step title="预览与映射" />
      <a-step title="导入结果" />
    </a-steps>

    <!-- Step 0: Upload -->
    <div v-if="step === 0">
      <a-upload
        draggable
        accept=".json"
        :auto-upload="false"
        :show-file-list="false"
        @change="onFileChange"
      >
        <template #upload-button>
          <div class="upload-area">
            <icon-upload :size="28" />
            <p>拖拽或点击上传 JSON 文件</p>
            <p v-if="selectedFile" class="upload-filename">{{ selectedFile.name }}</p>
          </div>
        </template>
      </a-upload>
    </div>

    <!-- Step 1: Preview + Datasource Mapping -->
    <div v-if="step === 1">
      <!-- Preview list -->
      <div class="preview-list">
        <div v-for="item in previewItems" :key="item.uuid || item.name" class="preview-item">
          <icon-check-circle v-if="item.status === 'new'" style="color: var(--color-success)" />
          <icon-exclamation-circle v-else style="color: var(--color-warning)" />
          <span class="preview-name">{{ item.name }}</span>
          <a-tag size="small">{{ item.type }}</a-tag>
          <a-tag size="small" :color="item.status === 'new' ? 'green' : 'orange'">
            {{ item.status === 'new' ? '新增' : '已存在' }}
          </a-tag>
        </div>
      </div>

      <!-- Datasource Mapping (v2 only) -->
      <div v-if="hasDatasources" class="ds-mapping-section">
        <div class="ds-mapping-header">
          <icon-link style="color: var(--color-primary)" />
          <span>数据源映射</span>
          <span class="ds-mapping-hint">将导出包中的数据源映射到本地环境</span>
        </div>
        <div class="ds-mapping-list">
          <div v-for="(info, dsName) in dsManifest" :key="dsName" class="ds-mapping-row">
            <div class="ds-mapping-source">
              <span class="ds-name">{{ dsName }}</span>
              <a-tag size="small" color="arcoblue">{{ info.type }}</a-tag>
            </div>
            <icon-arrow-right style="color: var(--color-text-disabled); flex-shrink: 0" />
            <a-select
              v-model="dsMapping[dsName as string]"
              placeholder="选择本地数据源"
              allow-search
              style="flex: 1; min-width: 180px"
            >
              <a-option
                v-for="ds in localDatasources.filter(d => d.type === info.type)"
                :key="ds.id"
                :value="ds.id"
              >
                {{ ds.name }}
              </a-option>
            </a-select>
          </div>
        </div>
      </div>

      <!-- Conflict strategy -->
      <div v-if="hasConflicts" class="strategy-row">
        <span>冲突处理：</span>
        <a-radio-group v-model="strategy">
          <a-radio value="skip">跳过</a-radio>
          <a-radio value="overwrite">覆盖</a-radio>
          <a-radio value="rename">重命名</a-radio>
        </a-radio-group>
      </div>
    </div>

    <!-- Step 2: Import Result -->
    <div v-if="step === 2">
      <div class="import-result">
        <div v-if="importResult" class="result-stats">
          <div v-if="importResult.created" class="result-stat">
            <icon-check-circle style="color: var(--color-success)" />
            <span class="result-ok">新增 {{ importResult.created }} 项</span>
          </div>
          <div v-if="importResult.updated" class="result-stat">
            <icon-sync style="color: var(--color-primary)" />
            <span class="result-ok">更新 {{ importResult.updated }} 项</span>
          </div>
          <div v-if="importResult.skipped" class="result-stat">
            <icon-minus-circle style="color: var(--color-text-tertiary)" />
            <span class="result-skip">跳过 {{ importResult.skipped }} 项</span>
          </div>
          <div v-if="importResult.errors?.length" class="result-stat">
            <icon-close-circle style="color: var(--color-danger)" />
            <span class="result-err">失败 {{ importResult.errors.length }} 项</span>
          </div>
        </div>
        <div v-if="importResult?.errors?.length" class="result-errors">
          <div v-for="(err, i) in importResult.errors" :key="i" class="result-error-item">
            {{ err }}
          </div>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <template #footer>
      <a-button v-if="step > 0 && step < 2" @click="step--">上一步</a-button>
      <a-button @click="reset">{{ step === 2 ? '关闭' : '取消' }}</a-button>
      <a-button
        v-if="step === 0"
        type="primary"
        :loading="previewing"
        :disabled="!selectedFile"
        @click="doPreview"
      >
        下一步
      </a-button>
      <a-button
        v-if="step === 1"
        type="primary"
        :loading="importing"
        :disabled="!canImport"
        @click="doImport"
      >
        确认导入
      </a-button>
    </template>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import {
  IconUpload, IconCheckCircle, IconExclamationCircle, IconLink,
  IconArrowRight, IconSync, IconMinusCircle, IconCloseCircle,
} from '@arco-design/web-vue/es/icon'
import { importBundle, previewImportBundle, getDatasources } from '../api'

interface PreviewItem {
  uuid?: string
  name: string
  type: string
  kind: string
  status: 'new' | 'exists'
}

interface DsManifestEntry {
  type: string
  description?: string
}

interface ImportResult {
  created?: number
  updated?: number
  skipped?: number
  errors?: string[]
}

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'imported'): void
}>()

const innerVisible = computed({
  get: () => props.visible,
  set: (val: boolean) => emit('update:visible', val),
})

const step = ref(0)
const selectedFile = ref<File | null>(null)
const previewing = ref(false)
const importing = ref(false)

const previewItems = ref<PreviewItem[]>([])
const dsManifest = ref<Record<string, DsManifestEntry>>({})
const formatVersion = ref('1.0')
const strategy = ref('skip')
const dsMapping = reactive<Record<string, number>>({})
const localDatasources = ref<any[]>([])
const importResult = ref<ImportResult | null>(null)

const hasConflicts = computed(() => previewItems.value.some(i => i.status === 'exists'))
const hasDatasources = computed(() => Object.keys(dsManifest.value).length > 0)
const isV2 = computed(() => formatVersion.value.startsWith('2'))

const canImport = computed(() => {
  if (!previewItems.value.length) return false
  if (hasDatasources.value) {
    // 所有数据源都必须映射
    return Object.keys(dsManifest.value).every(name => dsMapping[name])
  }
  return true
})

function onFileChange(fileList: any[], fileItem: any) {
  const file = fileItem?.file as File | undefined
  if (!file) return
  selectedFile.value = file
}

async function doPreview() {
  if (!selectedFile.value) return
  previewing.value = true
  try {
    const res: any = await previewImportBundle(selectedFile.value)
    previewItems.value = res.items || []
    dsManifest.value = res.datasources || {}
    formatVersion.value = res.format_version || '1.0'

    // 初始化映射
    Object.keys(dsMapping).forEach(k => delete dsMapping[k])

    // 如果有数据源需要映射，加载本地数据源列表
    if (Object.keys(dsManifest.value).length > 0) {
      try {
        const dsRes: any = await getDatasources({ page_size: 200 })
        localDatasources.value = dsRes?.items || dsRes || []
      } catch {
        localDatasources.value = []
      }
    }

    step.value = 1
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '预览失败')
  } finally {
    previewing.value = false
  }
}

async function doImport() {
  if (!selectedFile.value) return
  importing.value = true
  try {
    const mapping = hasDatasources.value ? { ...dsMapping } : undefined
    const res: any = await importBundle(selectedFile.value, strategy.value, mapping)
    importResult.value = res
    const created = res?.created || 0
    const updated = res?.updated || 0
    const skipped = res?.skipped || 0
    Message.success(`导入完成：新增 ${created}，更新 ${updated}，跳过 ${skipped}`)
    step.value = 2
    emit('imported')
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

function reset() {
  selectedFile.value = null
  previewItems.value = []
  dsManifest.value = {}
  formatVersion.value = '1.0'
  strategy.value = 'skip'
  Object.keys(dsMapping).forEach(k => delete dsMapping[k])
  localDatasources.value = []
  importing.value = false
  previewing.value = false
  importResult.value = null
  step.value = 0
  innerVisible.value = false
}

watch(() => props.visible, (val) => {
  if (val) {
    step.value = 0
    selectedFile.value = null
    previewItems.value = []
    dsManifest.value = {}
    formatVersion.value = '1.0'
    strategy.value = 'skip'
    Object.keys(dsMapping).forEach(k => delete dsMapping[k])
    localDatasources.value = []
    importing.value = false
    previewing.value = false
    importResult.value = null
  }
})
</script>

<style scoped>
.upload-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 16px;
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-md, 8px);
  background: var(--color-bg-base);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.upload-area:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
}
.upload-area p {
  margin: 0;
  font-size: var(--font-size-sm, 13px);
}
.upload-filename {
  color: var(--color-primary);
  font-weight: 500;
}

.preview-list {
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md, 8px);
}
.preview-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: var(--font-size-sm, 13px);
  border-bottom: 1px solid var(--color-border-subtle);
}
.preview-item:last-child {
  border-bottom: none;
}
.preview-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ─── Datasource Mapping ─── */
.ds-mapping-section {
  margin-top: 16px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md, 8px);
  overflow: hidden;
}
.ds-mapping-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--color-bg-base);
  font-size: var(--font-size-sm, 13px);
  font-weight: 500;
  color: var(--color-text-primary);
  border-bottom: 1px solid var(--color-border-subtle);
}
.ds-mapping-hint {
  font-weight: 400;
  color: var(--color-text-tertiary);
  margin-left: auto;
  font-size: 12px;
}
.ds-mapping-list {
  padding: 8px 14px;
}
.ds-mapping-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--color-border-subtle);
}
.ds-mapping-row:last-child {
  border-bottom: none;
}
.ds-mapping-source {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 160px;
}
.ds-name {
  font-size: var(--font-size-sm, 13px);
  font-weight: 500;
  color: var(--color-text-primary);
}

.strategy-row {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: var(--font-size-sm, 13px);
  color: var(--color-text-secondary);
}

/* ─── Import Result ─── */
.import-result {
  padding: 16px;
  background: var(--color-bg-base);
  border-radius: var(--radius-md, 8px);
}
.result-stats {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.result-stat {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-size-sm, 13px);
}
.result-ok { color: var(--color-success); font-weight: 500; }
.result-skip { color: var(--color-text-tertiary); }
.result-err { color: var(--color-danger); font-weight: 500; }
.result-errors {
  margin-top: 12px;
  padding: 10px;
  background: rgba(245, 63, 63, 0.05);
  border-radius: var(--radius-sm, 4px);
  font-size: 12px;
  color: var(--color-danger);
  max-height: 120px;
  overflow-y: auto;
}
.result-error-item {
  padding: 2px 0;
}
</style>
