<template>
  <div class="page">
    <PageHeader title="数据源管理" description="管理 MySQL、PostgreSQL、SQLServer、Oracle、ClickHouse 等数据源连接">
      <template #actions>
        <a-button type="primary" @click="showModal()">
          <template #icon><icon-plus /></template>
          新建数据源
        </a-button>
      </template>
    </PageHeader>

    <!-- 数据源列表 -->
    <div class="glass-card list-card">
      <div class="list-toolbar">
        <a-input-search v-model="keyword" placeholder="搜索数据源名称..." style="width: 280px;" @search="loadData" allow-clear />
      </div>

      <a-table :columns="columns" :data="dataSource" :loading="loading" :pagination="pagination"
        @page-change="onPageChange" @page-size-change="onPageSizeChange" style="margin-top: 12px;">
        <template #type="{ record }">
          <a-tag :color="typeColors[record.type] || 'blue'">{{ record.type.toUpperCase() }}</a-tag>
        </template>
        <template #status="{ record }">
          <div class="status-cell">
            <span class="status-dot" :class="record.status === 1 ? 'online' : 'offline'"></span>
            <span :style="{ color: record.status === 1 ? '#00B42A' : '#86909C' }">
              {{ record.status === 1 ? '正常' : '不可用' }}
            </span>
          </div>
        </template>
        <template #optional="{ record }">
          <a-space>
            <a-button type="text" size="small" @click="handleTest(record)">测试连接</a-button>
            <a-button type="text" size="small" @click="showModal(record)">编辑</a-button>
            <a-popconfirm content="确定删除此数据源？" @ok="handleDelete(record.id)">
              <a-button type="text" size="small" status="danger">删除</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </a-table>
    </div>

    <!-- 新建/编辑弹窗 -->
    <a-modal v-model:visible="modalVisible" :title="editingId ? '编辑数据源' : '新建数据源'"
      @ok="handleSubmit" :ok-loading="submitLoading" width="520px">
      <a-form :model="form" layout="vertical">
        <a-form-item field="name" label="数据源名称" :rules="[{ required: true }]">
          <a-input v-model="form.name" placeholder="如: 生产库-用户中心" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item field="type" label="数据库类型" :rules="[{ required: true }]">
              <a-select v-model="form.type" placeholder="选择类型" @change="onTypeChange">
                <a-option value="mysql">MySQL</a-option>
                <a-option value="postgresql">PostgreSQL</a-option>
                <a-option value="sqlserver">SQLServer</a-option>
                <a-option value="oracle">Oracle</a-option>
                <a-option value="clickhouse">ClickHouse</a-option>
                <a-option value="mongodb">MongoDB</a-option>
                <a-option value="redis">Redis</a-option>
                <a-option value="hive">Hive</a-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item field="port" label="端口" :rules="[{ required: true }]">
              <a-input-number v-model="form.port" placeholder="3306" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item field="host" label="主机地址" :rules="[{ required: true }]">
          <a-input v-model="form.host" placeholder="如: 192.168.1.100" />
        </a-form-item>
        <a-form-item field="database_name" label="数据库名" :rules="[{ required: true }]">
          <a-input v-model="form.database_name" placeholder="如: user_center" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item field="username" label="用户名">
              <a-input v-model="form.username" placeholder="数据库用户名" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item field="password" label="密码">
              <a-input-password v-model="form.password" placeholder="数据库密码" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item field="description" label="描述">
          <a-textarea v-model="form.description" placeholder="数据源用途说明..." :max-length="200" show-word-limit />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconPlus } from '@arco-design/web-vue/es/icon'
import PageHeader from '../components/PageHeader.vue'
import { getDatasources, createDatasource, updateDatasource, deleteDatasource, testDatasource } from '../api'

const loading = ref(false)
const submitLoading = ref(false)
const keyword = ref('')
const dataSource = ref<any[]>([])
const modalVisible = ref(false)
const editingId = ref<number | null>(null)
const pagination = reactive({ current: 1, pageSize: 10, total: 0, showTotal: true, showPageSize: true })

const form = reactive({
  name: '', type: 'mysql', host: '', port: 3306,
  database_name: '', username: '', password: '', description: '',
})

const typeColors: Record<string, string> = {
  mysql: 'blue', postgresql: 'cyan', sqlserver: 'purple',
  oracle: 'red', clickhouse: 'orange', mongodb: 'green',
  redis: 'orangered', hive: 'gold',
}

const defaultPorts: Record<string, number> = {
  mysql: 3306, postgresql: 5432, sqlserver: 1433,
  oracle: 1521, clickhouse: 8123, mongodb: 27017,
  redis: 6379, hive: 10000,
}

function onTypeChange(type: any) {
  form.port = defaultPorts[String(type)] || 3306
}

const columns = [
  { title: '名称', dataIndex: 'name', width: 180, ellipsis: true, tooltip: true },
  { title: '类型', dataIndex: 'type', slotName: 'type', width: 100 },
  { title: '主机', dataIndex: 'host', width: 200, ellipsis: true, tooltip: true },
  { title: '数据库', dataIndex: 'database_name', width: 140, ellipsis: true, tooltip: true },
  { title: '状态', dataIndex: 'status', slotName: 'status', width: 100 },
  { title: '创建时间', dataIndex: 'created_at', width: 170 },
  { title: '操作', slotName: 'optional', width: 200, fixed: 'right' as const },
]

onMounted(() => loadData())

async function loadData() {
  loading.value = true
  try {
    const res: any = await getDatasources({ page: pagination.current, page_size: pagination.pageSize, keyword: keyword.value || undefined })
    dataSource.value = res.items; pagination.total = res.total
  } catch {} finally { loading.value = false }
}

function onPageChange(page: number) { pagination.current = page; loadData() }
function onPageSizeChange(size: number) { pagination.pageSize = size; pagination.current = 1; loadData() }

function showModal(record?: any) {
  if (record) {
    editingId.value = record.id; Object.assign(form, record)
  } else {
    editingId.value = null
    Object.assign(form, { name: '', type: 'mysql', host: '', port: 3306, database_name: '', username: '', password: '', description: '' })
  }
  modalVisible.value = true
}

async function handleSubmit() {
  submitLoading.value = true
  try {
    if (editingId.value) { await updateDatasource(editingId.value, form); Message.success('更新成功') }
    else { await createDatasource(form); Message.success('创建成功') }
    modalVisible.value = false; loadData()
  } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') } finally { submitLoading.value = false }
}

async function handleTest(record: any) {
  try {
    const res: any = await testDatasource(record.id)
    if (res.status === 1) Message.success(res.message)
    else Message.warning(res.message)
    loadData()
  } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
}

async function handleDelete(id: number) {
  try { await deleteDatasource(id); Message.success('删除成功'); loadData() } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
}
</script>

<style scoped>
.page { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.list-card { padding: var(--space-5) var(--space-6); }
.list-toolbar { display: flex; justify-content: space-between; align-items: center; }

.status-cell { display: flex; align-items: center; gap: 6px; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; }
.status-dot.online { background: var(--color-success); box-shadow: 0 0 6px rgba(22,163,74,0.3); }
.status-dot.offline { background: var(--color-border-strong); }
</style>
