<template>
  <div class="page">
    <PageHeader title="补数据" description="查看历史补数任务进度。新建补数请到「工作流」页面，对目标工作流点「更多 → 补数」。" />

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
      <template #empty>
        <EmptyState description="暂无补数任务">
          <p class="text-muted">到「工作流」页面对目标工作流点「更多 → 补数」发起</p>
        </EmptyState>
      </template>
    </a-table>

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
import { ref, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import {
  listBackfill, getBackfill, stopBackfill, retryBackfillInstance,
} from '../api'

const loading = ref(false)
const list = ref<any[]>([])
const total = ref(0)
const page = ref(1)

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

function onPageChange(p: number) {
  page.value = p
  loadList()
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
})
</script>

<style scoped>
.page { padding: 16px; }
.text-muted { color: var(--color-text-tertiary); }
</style>
