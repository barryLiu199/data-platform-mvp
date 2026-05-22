<template>
  <a-drawer
    :visible="visible"
    title="项目管理"
    :width="480"
    unmount-on-close
    @cancel="close"
  >
    <template #footer>
      <a-button @click="close">关闭</a-button>
    </template>

    <!-- 新建表单 -->
    <div class="create-section">
      <div class="section-label">新建项目</div>
      <a-form :model="form" layout="inline" class="create-form">
        <a-form-item hide-label>
          <a-input v-model="form.name" placeholder="项目名称" style="width:140px" />
        </a-form-item>
        <a-form-item hide-label>
          <a-input v-model="form.code" placeholder="英文编码" style="width:120px" />
        </a-form-item>
        <a-form-item hide-label>
          <a-button type="primary" :loading="creating" @click="handleCreate">
            <template #icon><icon-plus /></template>
            创建
          </a-button>
        </a-form-item>
      </a-form>
    </div>

    <a-divider :margin="12" />

    <!-- 项目列表 -->
    <div class="project-list">
      <div v-for="p in list" :key="p.id" class="project-item" :class="{ editing: editId === p.id }">
        <span class="project-dot" :style="{ background: p.color }"></span>
        <template v-if="editId === p.id">
          <a-input v-model="editName" size="small" style="flex:1" @keyup.enter="handleUpdate" />
          <a-button type="text" size="mini" @click="handleUpdate" :loading="updating">
            <icon-check />
          </a-button>
          <a-button type="text" size="mini" @click="editId = 0">
            <icon-close />
          </a-button>
        </template>
        <template v-else>
          <span class="project-name">{{ p.name }}</span>
          <a-tag v-if="p.is_default" size="small" color="gray">默认</a-tag>
          <span class="project-stats">
            <span class="stat">{{ p.workflow_count ?? 0 }} 工作流</span>
            <span class="stat">{{ p.task_count ?? 0 }} 任务</span>
          </span>
          <a-space v-if="!p.is_default" :size="0" class="project-actions">
            <a-button type="text" size="mini" @click="startEdit(p)">
              <icon-edit />
            </a-button>
            <a-popconfirm
              content="删除后，项目下的工作流和任务将移入「未分组」"
              @ok="handleDelete(p.id)"
            >
              <a-button type="text" size="mini" status="danger">
                <icon-delete />
              </a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </div>
      <div v-if="!list.length" class="empty">暂无项目</div>
    </div>
  </a-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconPlus, IconEdit, IconDelete, IconCheck, IconClose } from '@arco-design/web-vue/es/icon'
import { getProjects, createProject, updateProject, deleteProject } from '../api'

interface ProjectItem {
  id: number
  name: string
  code: string
  color: string
  is_default: boolean
  task_count: number
  workflow_count: number
}

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'change'): void
}>()

const list = ref<ProjectItem[]>([])
const creating = ref(false)
const updating = ref(false)
const form = ref({ name: '', code: '' })
const editId = ref(0)
const editName = ref('')

watch(() => props.visible, async (v) => {
  if (v) await loadList()
})

async function loadList() {
  try {
    const res: any = await getProjects()
    list.value = (res?.items || []) as ProjectItem[]
  } catch {}
}

async function handleCreate() {
  if (!form.value.name) { Message.warning('请输入项目名称'); return }
  if (!form.value.code) { Message.warning('请输入英文编码'); return }
  creating.value = true
  try {
    await createProject({ name: form.value.name, code: form.value.code })
    Message.success('项目已创建')
    form.value = { name: '', code: '' }
    await loadList()
    emit('change')
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '创建失败')
  } finally { creating.value = false }
}

function startEdit(p: ProjectItem) {
  editId.value = p.id
  editName.value = p.name
}

async function handleUpdate() {
  if (!editName.value) { Message.warning('名称不能为空'); return }
  updating.value = true
  try {
    await updateProject(editId.value, { name: editName.value })
    Message.success('已更新')
    editId.value = 0
    await loadList()
    emit('change')
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '更新失败')
  } finally { updating.value = false }
}

async function handleDelete(id: number) {
  try {
    await deleteProject(id)
    Message.success('已删除')
    await loadList()
    emit('change')
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '删除失败')
  }
}

function close() {
  emit('update:visible', false)
}
</script>

<style scoped>
.create-section { padding: 0 0 4px; }
.section-label { font-size: 12px; color: var(--color-text-tertiary); margin-bottom: 8px; }
.create-form { display: flex; gap: 8px; align-items: flex-start; flex-wrap: wrap; }

.project-list { display: flex; flex-direction: column; gap: 2px; }
.project-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: 8px; transition: background 0.12s;
}
.project-item:hover { background: var(--color-fill-1); }
.project-item.editing { background: var(--color-fill-2); }

.project-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.project-name { font-size: 14px; font-weight: 500; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.project-stats { display: flex; gap: 8px; flex-shrink: 0; }
.stat { font-size: 11px; color: var(--color-text-tertiary); }
.project-actions { opacity: 0; transition: opacity 0.15s; flex-shrink: 0; }
.project-item:hover .project-actions { opacity: 1; }

.empty { text-align: center; color: var(--color-text-tertiary); padding: 32px 0; font-size: 13px; }
</style>
