<template>
  <a-modal v-model:visible="innerVisible" title="导入" :width="560" @cancel="reset">
    <!-- Upload area -->
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

    <!-- Preview list (shown after file selected) -->
    <div v-if="previewItems.length" class="preview-list">
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

    <!-- Conflict strategy -->
    <div v-if="hasConflicts" class="strategy-row">
      <span>冲突处理：</span>
      <a-radio-group v-model="strategy">
        <a-radio value="skip">跳过</a-radio>
        <a-radio value="overwrite">覆盖</a-radio>
        <a-radio value="rename">重命名</a-radio>
      </a-radio-group>
    </div>

    <!-- Import result -->
    <div v-if="importResult" class="import-result">
      <p v-if="importResult.created"><span class="result-ok">新增 {{ importResult.created }} 项</span></p>
      <p v-if="importResult.updated"><span class="result-ok">更新 {{ importResult.updated }} 项</span></p>
      <p v-if="importResult.skipped"><span class="result-skip">跳过 {{ importResult.skipped }} 项</span></p>
      <p v-if="importResult.errors?.length">
        <span class="result-err">失败 {{ importResult.errors.length }} 项</span>
      </p>
    </div>

    <!-- Footer -->
    <template #footer>
      <a-button @click="reset">取消</a-button>
      <a-button type="primary" :loading="importing" :disabled="!selectedFile || !!importResult" @click="doImport">
        确认导入
      </a-button>
    </template>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconUpload, IconCheckCircle, IconExclamationCircle } from '@arco-design/web-vue/es/icon'
import { importBundle } from '../api'

interface PreviewItem {
  uuid?: string
  name: string
  type: string
  status: 'new' | 'exists'
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

const selectedFile = ref<File | null>(null)
const previewItems = ref<PreviewItem[]>([])
const strategy = ref('skip')
const importing = ref(false)
const importResult = ref<ImportResult | null>(null)

const hasConflicts = computed(() => previewItems.value.some(i => i.status === 'exists'))

function onFileChange(fileList: any[], fileItem: any) {
  const file = fileItem?.file as File | undefined
  if (!file) return
  selectedFile.value = file
  importResult.value = null

  // Parse JSON to show preview
  const reader = new FileReader()
  reader.onload = (ev) => {
    try {
      const data = JSON.parse(ev.target?.result as string)
      const items: PreviewItem[] = []
      const bundleType = data.type  // "component" or "workflow"
      const entries = data.items || []

      if (bundleType === 'workflow') {
        // Workflow bundle: items are workflows, each may contain inline components
        for (const wf of entries) {
          items.push({
            uuid: wf.uuid,
            name: wf.name || '未命名',
            type: '工作流',
            status: 'new',
          })
          for (const comp of (wf.components || [])) {
            items.push({
              uuid: comp.uuid,
              name: comp.name || '未命名',
              type: comp.type || 'component',
              status: 'new',
            })
          }
        }
      } else {
        // Component bundle
        for (const entry of entries) {
          items.push({
            uuid: entry.uuid,
            name: entry.name || '未命名',
            type: entry.type || 'component',
            status: 'new',
          })
        }
      }
      previewItems.value = items
    } catch {
      previewItems.value = []
      Message.warning('无法解析 JSON 文件')
    }
  }
  reader.readAsText(file)
}

async function doImport() {
  if (!selectedFile.value) return
  importing.value = true
  try {
    const res: any = await importBundle(selectedFile.value, strategy.value)
    importResult.value = res
    const created = res?.created || 0
    const updated = res?.updated || 0
    const skipped = res?.skipped || 0
    Message.success(`导入完成：新增 ${created}，更新 ${updated}，跳过 ${skipped}`)
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
  strategy.value = 'skip'
  importing.value = false
  importResult.value = null
  innerVisible.value = false
}

// Reset state when modal opens
watch(() => props.visible, (val) => {
  if (val) {
    selectedFile.value = null
    previewItems.value = []
    strategy.value = 'skip'
    importing.value = false
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
  margin-top: 16px;
  max-height: 240px;
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

.strategy-row {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: var(--font-size-sm, 13px);
  color: var(--color-text-secondary);
}

.import-result {
  margin-top: 16px;
  padding: 12px;
  background: var(--color-bg-base);
  border-radius: var(--radius-md, 8px);
  font-size: var(--font-size-sm, 13px);
}
.import-result p { margin: 4px 0; }
.result-ok { color: var(--color-success); font-weight: 500; }
.result-skip { color: var(--color-text-tertiary); }
.result-err { color: var(--color-danger); font-weight: 500; }
</style>
