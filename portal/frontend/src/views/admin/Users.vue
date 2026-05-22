<template>
  <div class="admin-page">
    <PageHeader title="用户管理">
      <template #actions>
        <a-button type="primary" @click="openCreate">
          <template #icon><icon-plus /></template>
          新建用户
        </a-button>
      </template>
    </PageHeader>

    <a-card :bordered="false">
      <div class="toolbar">
        <a-input-search
          v-model="keyword"
          placeholder="搜索用户名/姓名"
          style="width: 240px"
          @search="loadUsers"
          allow-clear
        />
      </div>

      <a-table
        :data="users"
        :loading="loading"
        :pagination="{ total, pageSize, current: page }"
        @page-change="onPageChange"
        row-key="id"
        style="margin-top: 12px"
      >
        <template #columns>
          <a-table-column title="用户名" data-index="username" />
          <a-table-column title="姓名" data-index="real_name" />
          <a-table-column title="邮箱" data-index="email" />
          <a-table-column title="角色">
            <template #cell="{ record }">
              <a-space wrap>
                <a-tag v-for="r in record.roles" :key="r.id" color="arcoblue" size="small">{{ r.name }}</a-tag>
                <span v-if="!record.roles?.length" style="color: #C9CDD4">—</span>
              </a-space>
            </template>
          </a-table-column>
          <a-table-column title="状态">
            <template #cell="{ record }">
              <a-badge :status="record.status === 1 ? 'success' : 'danger'" :text="record.status === 1 ? '正常' : '禁用'" />
            </template>
          </a-table-column>
          <a-table-column title="最近登录" data-index="last_login_at" />
          <a-table-column title="操作" :width="160">
            <template #cell="{ record }">
              <a-space>
                <a-button type="text" size="small" @click="openEdit(record)">编辑</a-button>
                <a-button
                  type="text"
                  size="small"
                  status="danger"
                  :disabled="record.username === 'admin'"
                  @click="handleDelete(record)"
                >删除</a-button>
              </a-space>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </a-card>

    <!-- 新建/编辑抽屉 -->
    <a-drawer
      v-model:visible="drawerVisible"
      :title="editingUser ? '编辑用户' : '新建用户'"
      :width="480"
      @ok="handleSubmit"
      @cancel="drawerVisible = false"
    >
      <a-form :model="form" layout="vertical">
        <a-form-item label="用户名" required>
          <a-input v-model="form.username" :disabled="!!editingUser" placeholder="登录用户名" />
        </a-form-item>
        <a-form-item :label="editingUser ? '新密码（留空不修改）' : '密码'" :required="!editingUser">
          <a-input-password v-model="form.password" placeholder="请输入密码" />
        </a-form-item>
        <a-form-item label="姓名">
          <a-input v-model="form.real_name" placeholder="真实姓名" />
        </a-form-item>
        <a-form-item label="邮箱">
          <a-input v-model="form.email" placeholder="邮箱地址" />
        </a-form-item>
        <a-form-item label="手机">
          <a-input v-model="form.phone" placeholder="手机号码" />
        </a-form-item>
        <a-form-item label="角色">
          <a-select
            v-model="form.role_codes"
            multiple
            placeholder="选择角色"
            :options="roleOptions"
          />
        </a-form-item>
        <a-form-item v-if="editingUser" label="状态">
          <a-radio-group v-model="form.status">
            <a-radio :value="1">正常</a-radio>
            <a-radio :value="0">禁用</a-radio>
          </a-radio-group>
        </a-form-item>
      </a-form>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { IconPlus } from '@arco-design/web-vue/es/icon'
import {
  adminListUsers, adminCreateUser, adminUpdateUser, adminDeleteUser, adminListRoles,
} from '../../api'
import PageHeader from '../../components/PageHeader.vue'

const loading = ref(false)
const users = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const keyword = ref('')

const drawerVisible = ref(false)
const editingUser = ref<any>(null)
const form = ref<any>({})
const roleOptions = ref<any[]>([])

async function loadUsers() {
  loading.value = true
  try {
    const res: any = await adminListUsers({ page: page.value, page_size: pageSize, keyword: keyword.value || undefined })
    users.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

async function loadRoles() {
  const res: any = await adminListRoles()
  roleOptions.value = (res || []).map((r: any) => ({ label: r.name, value: r.code }))
}

function onPageChange(p: number) {
  page.value = p
  loadUsers()
}

function openCreate() {
  editingUser.value = null
  form.value = { username: '', password: '', real_name: '', email: '', phone: '', role_codes: [], status: 1 }
  drawerVisible.value = true
}

function openEdit(user: any) {
  editingUser.value = user
  form.value = {
    real_name: user.real_name || '',
    email: user.email || '',
    phone: user.phone || '',
    password: '',
    role_codes: (user.roles || []).map((r: any) => r.code),
    status: user.status,
  }
  drawerVisible.value = true
}

async function handleSubmit() {
  try {
    if (editingUser.value) {
      const payload: any = { ...form.value }
      if (!payload.password) delete payload.password
      await adminUpdateUser(editingUser.value.id, payload)
      Message.success('更新成功')
    } else {
      await adminCreateUser(form.value)
      Message.success('创建成功')
    }
    drawerVisible.value = false
    loadUsers()
  } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
}

function handleDelete(user: any) {
  Modal.confirm({
    title: `确认删除用户 "${user.username}"？`,
    content: '此操作不可恢复',
    onOk: async () => {
      try {
        await adminDeleteUser(user.id)
        Message.success('已删除')
        loadUsers()
      } catch (e: any) { Message.error(e?.response?.data?.detail || '操作失败') }
    },
  })
}

onMounted(() => {
  loadUsers()
  loadRoles()
})
</script>

<style scoped>
.admin-page { padding: 0; }
.toolbar { display: flex; gap: 12px; }
</style>
