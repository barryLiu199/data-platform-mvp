<template>
  <div class="page">
    <PageHeader title="补数据" description="按日期范围批量补跑工作流，支持并行/串行执行">
      <template #extra>
        <a-button type="primary" @click="creatorVisible = true">
          <template #icon><icon-plus /></template>
          新建补数据
        </a-button>
      </template>
    </PageHeader>

    <a-table
      :data="list"
      :loading="loading"
      :pagination="{ pageSize: 20, showTotal: true, total }"
      row-key="id"
      style="margin-top: 12px"
      @page-change="onPageChange"
    >
      <template #columns>
        <a-table-column title="工作流" data-index="workflow_name" />
        <a-table-column title="日期范围">
          <template #cell="{ record }">{{ record.date_from }} ~ {{ record.date_to }}</template>
        </a-table-column>
        <a-table-column title="并行" data-index="parallel" :width="80" />
        <a-table-column title="依赖" :width="80">
          <template #cell="{ record }">
            <a-tag :color="record.has_dep ? 'orange' : 'green'">
              {{ record.has_dep ? '串行' : '并行' }}
            </a-tag>
          </template>
        </a-table-column>
        <a-table-column title="进度" :width="180">
          <template #cell="{ record }">
            <a-progress
              :percent="record.total_count ? Math.round((record.success_count + record.failed_count) / record.total_count * 100) : 0"
              :status="record.failed_count > 0 ? 'danger' : 'normal'"
              size="small"
            />
            <div style="font-size:12px;color:var(--color-text-3)">
              {{ record.success_count }} 成功 / {{ record.failed_count }} 失败 / {{ record.total_count }} 总
            </div>
          </template>
        </a-table-column>
        <a-table-column title="状态" :width="100">
          <template #cell="{ record }">
            <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="创建时间" data-index="created_at" :width="170" />
        <a-table-column title="操作" :width="160">
          <template #cell="{ record }">
            <a-button type="text" size="small" @click="openDetail(record.id)">详情</a-button>
            <a-popconfirm content="确认停止？" @ok="onStop(record.id)" v-if="['pending','running'].includes(record.status)">
              <a-button type="text" status="danger" size="small">停止</a-button>
            </a-popconfirm>
          </template>
        </a-table-column>
      </template>
    </a-table>

    <!-- 新建抽屉 -->
    <a-modal v-model:visible="creatorVisible" title="新建补数据" :width="560" @ok="onCreate" :ok-loading="submitting">
      <a-form :model="form" auto-label-width>
        <a-form-item field="workflow_id" label="工作流" :rules="[{ required: true, message: '请选择工作流' }]">
          <a-select v-model="form.workflow_id" placeholder="选择已发布的工作流" :loading="wfLoading">
            <a-option v-for="w in workflows" :key="w.id" :value="w.id">{{ w.name }}</a-option>
          </a-select>
        </a-form-item>
        <a-form-item field="date_range" label="日期范围" :rules="[{ required: true, message: '请选择日期范围' }]">
          <a-range-picker v-model="form.date_range" style="width: 100%" />
        </a-form-item>
        <a-form-item field="has_dep" label="日期依赖">
          <a-switch v-model="form.has_dep" />
          <span style="margin-left:8px;color:var(--color-text-3);font-size:12px">
            {{ form.has_dep ? '串行：按日顺序，失败停止' : '并行：受并行度限制' }}
          </span>
        </a-form-item>
        <a-form-item field="parallel" label="并行度" :disabled="form.has_dep">
          <a-input-number v-model="form.parallel" :min="1" :max="20" :disabled="form.has_dep" />
        </a-form-item>
        <a-form-item label="预计实例数">
          <span>{{ estimateCount }} 个</span>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 详情抽屉 -->
    <a-drawer v-model:visible="detailVisible" :width="640" title="补数据详情" :footer="false">
      <div v-if="detail">
        <div style="margin-bottom:12px">
          <b>{{ detail.workflow_name }}</b>
          &nbsp;<a-tag :color="statusColor(detail.status)">{{ detail.status }}</a-tag>
          <div style="color:var(--color-text-3);font-size:12px;margin-top:4px">
            {{ detail.date_from }} ~ {{ detail.date_to }} ·
            {{ detail.has_dep ? '串行' : `并行=${detail.parallel}` }} ·
            成功 {{ detail.success_count }} / 失败 {{ detail.failed_count }} / 总 {{ detail.total_count }}
          </div>
        </div>
        <a-table :data="detail.instances" :pagination="false" row-key="id" size="small">
          <template #columns>
            <a-table-column title="#" data-index="seq" :width="50" />
            <a-table-column title="运行日期" data-index="run_date" />
            <a-table-column title="状态" :width="100">
              <template #cell="{ record }">
                <a-tag :color="instStatusColor(record.status)">{{ record.status }}</a-tag>
              </template>
            </a-table-column>
            <a-table-column title="开始" data-index="started_at" />
            <a-table-column title="结束" data-index="finished_at" />
            <a-table-column title="操作" :width="80">
              <template #cell="{ record }">
                <a-button
                  v-if="['failed','skipped'].includes(record.status)"
                  type="text"
                  size="small"
                  @click="onRetry(record.id)"
                >重试</a-button>
              </template>
            </a-table-column>
          </template>
        </a-table>
      </div>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconPlus } from '@arco-design/web-vue/es/icon'
import PageHeader from '../components/PageHeader.vue'
import {
  listBackfill, createBackfill, getBackfill, stopBackfill, retryBackfillInstance,
  getWorkflows,
} from '../api'

const loading = ref(false)
const list = ref<any[]>([])
const total = ref(0)
const page = ref(1)

const creatorVisible = ref(false)
const submitting = ref(false)
const wfLoading = ref(false)
const workflows = ref<any[]>([])

const form = reactive({
  workflow_id: undefined as number | undefined,
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

const detailVisible = ref(false)
const detail = ref<any>(null)

function statusColor(s: string): string {
  return ({ pending: 'gray', running: 'blue', succeeded: 'green', failed: 'red', stopping: 'orange', stopped: 'orange' } as any)[s] || 'gray'
}
function instStatusColor(s: string): string {
  return ({ pending: 'gray', running: 'blue', success: 'green', failed: 'red', skipped: 'orange' } as any)[s] || 'gray'
}

async function loadList() {
  loading.value = true
  try {
    const res = await listBackfill({ page: page.value, page_size: 20 })
    list.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

async function loadWorkflows() {
  wfLoading.value = true
  try {
    const res = await getWorkflows({ status: 'online', page_size: 200 })
    workflows.value = res.data.items || []
  } finally {
    wfLoading.value = false
  }
}

function onPageChange(p: number) {
  page.value = p
  loadList()
}

async function onCreate() {
  if (!form.workflow_id || form.date_range?.length !== 2) {
    Message.warning('请选择工作流和日期范围')
    return
  }
  submitting.value = true
  try {
    await createBackfill({
      workflow_id: form.workflow_id,
      date_from: form.date_range[0],
      date_to: form.date_range[1],
      parallel: form.has_dep ? 1 : form.parallel,
      has_dep: form.has_dep ? 1 : 0,
    })
    Message.success('已创建并开始执行')
    creatorVisible.value = false
    form.workflow_id = undefined
    form.date_range = []
    form.parallel = 1
    form.has_dep = false
    loadList()
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '创建失败')
  } finally {
    submitting.value = false
  }
}

async function openDetail(id: number) {
  const res = await getBackfill(id)
  detail.value = res.data
  detailVisible.value = true
}

async function onStop(id: number) {
  await stopBackfill(id)
  Message.success('已请求停止')
  loadList()
}

async function onRetry(id: number) {
  await retryBackfillInstance(id)
  Message.success('已重新加入队列')
  if (detail.value) openDetail(detail.value.id)
}

onMounted(() => {
  loadList()
  loadWorkflows()
})
</script>

<style scoped>
.page { padding: 16px; }
</style>
