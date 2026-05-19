<template>
  <div class="admin-page">
    <PageHeader title="角色管理">
      <template #actions>
        <a-button type="primary" @click="openCreate">
          <template #icon><icon-plus /></template>
          新建角色
        </a-button>
      </template>
    </PageHeader>

    <a-row :gutter="16">
      <!-- 角色列表 -->
      <a-col :span="8">
        <a-card :bordered="false" title="角色列表">
          <a-list :data="roles" :loading="loading">
            <template #item="{ item }">
              <a-list-item
                class="role-item"
                :class="{ active: selectedRole?.id === item.id }"
                @click="selectRole(item)"
              >
                <div class="role-info">
                  <span class="role-name">{{ item.name }}</span>
                  <a-tag v-if="item.is_system" size="small" color="orange">内置</a-tag>
                </div>
                <div class="role-desc">{{ item.description || '—' }}</div>
                <template #actions>
                  <a-button
                    v-if="!item.is_system"
                    type="text"
                    size="mini"
                    status="danger"
                    @click.stop="handleDelete(item)"
                  >删除</a-button>
                </template>
              </a-list-item>
            </template>
          </a-list>
        </a-card>
      </a-col>

      <!-- 权限配置 -->
      <a-col :span="16">
        <a-card :bordered="false" :title="selectedRole ? `${selectedRole.name} — 权限配置` : '选择角色查看权限'">
          <template v-if="selectedRole">
            <div v-for="group in permissionGroups" :key="group.type" class="perm-group">
              <div class="perm-group-title">{{ group.label }}</div>
              <a-space wrap>
                <a-checkbox
                  v-for="p in group.perms"
                  :key="p.code"
                  :model-value="selectedPerms.includes(p.code)"
                  :disabled="selectedRole.is_system"
                  @change="(v: boolean) => togglePerm(p.code, v)"
                >{{ p.name }}</a-checkbox>
              </a-space>
            </div>
            <div v-if="!selectedRole.is_system" style="margin-top: 16px">
              <a-button type="primary" @click="savePerms" :loading="saving">保存权限</a-button>
            </div>
          </template>
          <a-empty v-else description="请从左侧选择角色" />
        </a-card>
      </a-col>
    </a-row>

    <!-- 新建角色弹窗 -->
    <a-modal v-model:visible="createVisible" title="新建角色" @ok="handleCreate" @cancel="createVisible = false">
      <a-form :model="createForm" layout="vertical">
        <a-form-item label="角色代码" required>
          <a-input v-model="createForm.code" placeholder="如 custom_analyst" />
        </a-form-item>
        <a-form-item label="角色名称" required>
          <a-input v-model="createForm.name" placeholder="显示名称" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model="createForm.description" :max-length="255" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { IconPlus } from '@arco-design/web-vue/es/icon'
import { adminListRoles, adminCreateRole, adminUpdateRole, adminDeleteRole, adminListPermissions } from '../../api'
import PageHeader from '../../components/PageHeader.vue'

const loading = ref(false)
const saving = ref(false)
const roles = ref<any[]>([])
const allPerms = ref<any[]>([])
const selectedRole = ref<any>(null)
const selectedPerms = ref<string[]>([])

const createVisible = ref(false)
const createForm = ref({ code: '', name: '', description: '' })

const permissionGroups = computed(() => {
  const groups: Record<string, { label: string; perms: any[] }> = {
    user: { label: '用户与角色', perms: [] },
    system: { label: '系统配置', perms: [] },
    datasource: { label: '数据源', perms: [] },
    component: { label: '组件', perms: [] },
    workflow: { label: '工作流', perms: [] },
    sync: { label: '数据同步', perms: [] },
    metadata: { label: '数据资产', perms: [] },
    monitor: { label: '系统监控', perms: [] },
  }
  const labels: Record<string, string> = {
    user: '用户与角色', role: '用户与角色', system: '系统配置',
    datasource: '数据源', component: '组件', workflow: '工作流',
    sync: '数据同步', metadata: '数据资产', monitor: '系统监控',
  }
  for (const p of allPerms.value) {
    const key = p.resource_type || 'other'
    if (!groups[key]) groups[key] = { label: labels[key] || key, perms: [] }
    groups[key].perms.push(p)
  }
  return Object.values(groups).filter(g => g.perms.length > 0)
})

async function loadRoles() {
  loading.value = true
  try {
    roles.value = (await adminListRoles() as any) || []
  } finally {
    loading.value = false
  }
}

async function loadPerms() {
  allPerms.value = (await adminListPermissions() as any) || []
}

function selectRole(role: any) {
  selectedRole.value = role
  selectedPerms.value = (role.permissions || []).map((p: any) => p.code)
}

function togglePerm(code: string, checked: boolean) {
  if (checked) {
    if (!selectedPerms.value.includes(code)) selectedPerms.value.push(code)
  } else {
    selectedPerms.value = selectedPerms.value.filter(c => c !== code)
  }
}

async function savePerms() {
  saving.value = true
  try {
    await adminUpdateRole(selectedRole.value.id, { permission_codes: selectedPerms.value })
    Message.success('权限已保存')
    await loadRoles()
    const updated = roles.value.find(r => r.id === selectedRole.value.id)
    if (updated) selectRole(updated)
  } finally {
    saving.value = false
  }
}

function openCreate() {
  createForm.value = { code: '', name: '', description: '' }
  createVisible.value = true
}

async function handleCreate() {
  await adminCreateRole(createForm.value)
  Message.success('角色已创建')
  createVisible.value = false
  loadRoles()
}

function handleDelete(role: any) {
  Modal.confirm({
    title: `确认删除角色 "${role.name}"？`,
    onOk: async () => {
      await adminDeleteRole(role.id)
      Message.success('已删除')
      if (selectedRole.value?.id === role.id) selectedRole.value = null
      loadRoles()
    },
  })
}

onMounted(() => {
  loadRoles()
  loadPerms()
})
</script>

<style scoped>
.admin-page { padding: 0; }
.role-item { cursor: pointer; border-radius: 6px; padding: 8px 12px; transition: background 0.15s; }
.role-item:hover { background: #F7F8FA; }
.role-item.active { background: #EFF4FF; }
.role-info { display: flex; align-items: center; gap: 8px; }
.role-name { font-weight: 500; color: #1D2129; }
.role-desc { font-size: 12px; color: #86909C; margin-top: 2px; }
.perm-group { margin-bottom: 16px; }
.perm-group-title { font-size: 13px; font-weight: 600; color: #4E5969; margin-bottom: 8px; }
</style>
