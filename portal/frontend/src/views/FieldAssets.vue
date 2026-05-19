<template>
  <div class="page">
    <PageHeader title="词根管理" description="数据命名规范化 — 统一词根库，建表命名有据可依">
      <template #actions>
        <a-space>
          <a-input-search v-model="keyword" placeholder="搜索中文/英文..." style="width:200px" @search="loadData" allow-clear @clear="loadData" />
          <a-upload :show-file-list="false" accept=".xlsx,.xls" :custom-request="handleImport">
            <template #upload-button>
              <a-button><icon-upload /> 导入 Excel</a-button>
            </template>
          </a-upload>
          <a-button type="primary" @click="openCreate"><icon-plus /> 新建</a-button>
        </a-space>
      </template>
    </PageHeader>

    <FilterTabs v-model="catFilter" :tabs="catTabs" @update:model-value="setCat" />

    <!-- 命名建议器 -->
    <div class="glass-card suggest-card">
      <div class="suggest-row">
        <span class="suggest-label">命名建议器</span>
        <a-input v-model="suggestInput" placeholder="输入中文，如：用户订单金额" style="flex:1;max-width:300px" @input="doSuggest" />
        <span class="suggest-result" v-if="suggestResult">
          <span class="suggest-arrow">→</span>
          <code class="suggest-code">{{ suggestResult }}</code>
        </span>
      </div>
      <div class="suggest-matches" v-if="suggestMatches.length">
        <a-tag v-for="m in suggestMatches" :key="m.cn" size="small" color="arcoblue">{{ m.cn }} = {{ m.en }}</a-tag>
      </div>
    </div>

    <!-- 表格 -->
    <div class="glass-card table-card">
      <a-table :data="items" :loading="loading" :bordered="false" :pagination="false" stripe>
        <template #columns>
          <a-table-column title="英文词根" data-index="en" :width="120">
            <template #cell="{ record }"><code class="root-code">{{ record.en }}</code></template>
          </a-table-column>
          <a-table-column title="中文名" data-index="cn" :width="100" />
          <a-table-column title="分类" :width="100">
            <template #cell="{ record }">
              <a-tag :color="catColor(record.category)" size="small">{{ catLabel(record.category) }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="说明" data-index="description" :width="200" :ellipsis="true" :tooltip="true" />
          <a-table-column title="示例用法" :width="200">
            <template #cell="{ record }">
              <code class="example-code">{{ record.example || '—' }}</code>
            </template>
          </a-table-column>
          <a-table-column title="操作" :width="120">
            <template #cell="{ record }">
              <a-space :size="4">
                <a-button type="text" size="mini" @click="openEdit(record)">编辑</a-button>
                <a-button type="text" size="mini" status="danger" @click="handleDelete(record)">删除</a-button>
              </a-space>
            </template>
          </a-table-column>
        </template>
        <template #empty>
          <div class="empty-state">
            <p>暂无词根</p>
            <p class="text-muted">点击「导入 Excel」批量导入或「新建」逐条添加</p>
          </div>
        </template>
      </a-table>
      <div class="pagination-wrap" v-if="total > pageSize">
        <a-pagination v-model:current="page" :total="total" :page-size="pageSize" show-total @change="loadData" />
      </div>
    </div>

    <!-- 新建/编辑 -->
    <a-modal v-model:visible="modalVisible" :title="editingId ? '编辑词根' : '新建词根'" :width="480" @ok="handleSave" :unmount-on-close="true">
      <a-form :model="form" layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="英文词根" required>
              <a-input v-model="form.en" placeholder="如 user, order, amt" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="中文名" required>
              <a-input v-model="form.cn" placeholder="如 用户, 订单, 金额" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="分类">
          <a-select v-model="form.category">
            <a-option value="business">业务词根</a-option>
            <a-option value="technical">技术词根</a-option>
            <a-option value="metric">度量词根</a-option>
          </a-select>
        </a-form-item>
        <a-form-item label="说明">
          <a-input v-model="form.description" placeholder="可选" />
        </a-form-item>
        <a-form-item label="示例用法">
          <a-input v-model="form.example" placeholder="如 user_info, user_id" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { IconPlus, IconUpload } from '@arco-design/web-vue/es/icon'
import { getWordRoots, createWordRoot, updateWordRoot, deleteWordRoot, importWordRoots, suggestNaming } from '../api'
import PageHeader from '../components/PageHeader.vue'
import FilterTabs from '../components/FilterTabs.vue'
import type { FilterTab } from '../components/FilterTabs.vue'

const loading = ref(false)
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const keyword = ref('')
const catFilter = ref('')

const modalVisible = ref(false)
const editingId = ref<number | null>(null)
const form = ref({ en: '', cn: '', category: 'business', description: '', example: '' })

const suggestInput = ref('')
const suggestResult = ref('')
const suggestMatches = ref<any[]>([])

function catColor(c: string) { return ({ business: 'blue', technical: 'orange', metric: 'green' } as any)[c] || 'gray' }
function catLabel(c: string) { return ({ business: '业务词根', technical: '技术词根', metric: '度量词根' } as any)[c] || c }
function setCat(c: string) { catFilter.value = c; loadData() }

const catTabs = computed<FilterTab[]>(() => [
  { label: '全部', value: '', count: total.value },
  { label: '业务词根', value: 'business' },
  { label: '技术词根', value: 'technical' },
  { label: '度量词根', value: 'metric' },
])

async function loadData() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (catFilter.value) params.category = catFilter.value
    const res: any = await getWordRoots(params)
    items.value = res?.items || []
    total.value = res?.total || 0
  } catch { items.value = []; total.value = 0 }
  loading.value = false
}

function openCreate() {
  editingId.value = null
  form.value = { en: '', cn: '', category: 'business', description: '', example: '' }
  modalVisible.value = true
}
function openEdit(r: any) {
  editingId.value = r.id
  form.value = { en: r.en, cn: r.cn, category: r.category, description: r.description || '', example: r.example || '' }
  modalVisible.value = true
}

async function handleSave() {
  if (!form.value.en.trim() || !form.value.cn.trim()) { Message.warning('英文词根和中文名必填'); return }
  try {
    if (editingId.value) {
      await updateWordRoot(editingId.value, form.value)
      Message.success('已更新')
    } else {
      await createWordRoot(form.value)
      Message.success('已创建')
    }
    modalVisible.value = false
    loadData()
  } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
}

function handleDelete(r: any) {
  Modal.confirm({
    title: '删除词根', content: `确认删除「${r.en}」?`,
    onOk: async () => { try { await deleteWordRoot(r.id); Message.success('已删除'); loadData() } catch {} },
  })
}

function handleImport(option: any) {
  importWordRoots(option.fileItem.file)
    .then((res: any) => {
      Message.success(`导入完成：新增 ${res.created} 条，跳过 ${res.skipped} 条`)
      loadData()
    })
    .catch((e: any) => { Message.error(e?.response?.data?.detail || '导入失败') })
  return { abort: () => {} }
}

let suggestTimer: any = null
function doSuggest() {
  clearTimeout(suggestTimer)
  if (!suggestInput.value.trim()) { suggestResult.value = ''; suggestMatches.value = []; return }
  suggestTimer = setTimeout(async () => {
    try {
      const res: any = await suggestNaming(suggestInput.value)
      suggestResult.value = res.suggestion || ''
      suggestMatches.value = res.matches || []
    } catch {}
  }, 300)
}

onMounted(() => { loadData() })
</script>

<style scoped>
.page { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.suggest-card { padding: 14px 20px; margin-bottom: 12px; }
.suggest-row { display: flex; align-items: center; gap: 12px; }
.suggest-label { font-size: 13px; color: var(--color-text-secondary); font-weight: 500; white-space: nowrap; }
.suggest-arrow { color: var(--color-text-tertiary); margin: 0 4px; }
.suggest-code { font-family: var(--font-family-mono); font-size: 14px; color: var(--color-primary); font-weight: 600; }
.suggest-matches { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }

.table-card { padding: 0; overflow: auto; }
.root-code { font-family: var(--font-family-mono); font-size: 13px; color: var(--color-text-primary); font-weight: 500; }
.example-code { font-family: var(--font-family-mono); font-size: 12px; color: var(--color-text-tertiary); }
.text-muted { color: var(--color-text-tertiary); }
.empty-state { padding: 40px 0; text-align: center; }
.pagination-wrap { padding: 16px 24px; display: flex; justify-content: flex-end; border-top: 1px solid var(--color-border-subtle); }
:deep(.arco-table-th) { background: var(--color-bg-elevated) !important; }
</style>
