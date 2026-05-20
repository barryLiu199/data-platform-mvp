import axios from 'axios'
import { Message } from '@arco-design/web-vue'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  withCredentials: true,  // 自动携带 httponly cookie
})

api.interceptors.request.use((config) => {
  return config
})

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const msg = error.response?.data?.detail || '请求失败'
    if (error.response?.status === 401) {
      // 清除 Pinia 内存状态，避免刷新后 beforeEach 误判为已登录
      import('../stores/user').then(({ useUserStore }) => {
        useUserStore().logout()
      })
      window.location.href = '/login'
    } else {
      Message.error(msg)
    }
    return Promise.reject(error)
  }
)

// Auth
export const login = (data: { username: string; password: string }) =>
  api.post('/auth/login', data)

export const logout = () => api.post('/auth/logout')
export const getMe = () => api.get('/auth/me')
export const getMyPermissions = () => api.get('/auth/me/permissions')

// Dashboard
export const getDashboardStats = () => api.get('/dashboard/stats')

// DataSources
export const getDatasources = (params?: any) => api.get('/datasources', { params })
export const getDatasource = (id: number) => api.get(`/datasources/${id}`)
export const createDatasource = (data: any) => api.post('/datasources', data)
export const updateDatasource = (id: number, data: any) => api.put(`/datasources/${id}`, data)
export const deleteDatasource = (id: number) => api.delete(`/datasources/${id}`)
export const testDatasource = (id: number) => api.post(`/datasources/${id}/test`)

// Sync Tasks
export const getSyncTasks = (params?: any) => api.get('/sync-tasks', { params })
export const getSyncTask = (id: number) => api.get(`/sync-tasks/${id}`)
export const createSyncTask = (data: any) => api.post('/sync-tasks', data)
export const updateSyncTask = (id: number, data: any) => api.put(`/sync-tasks/${id}`, data)
export const deleteSyncTask = (id: number) => api.delete(`/sync-tasks/${id}`)
export const setSyncTaskStatus = (id: number, status: string) => api.patch(`/sync-tasks/${id}/status`, null, { params: { status } })
export const previewSyncTaskDataX = (id: number) => api.get(`/sync-tasks/${id}/preview-datax`)
export const previewSyncTaskUnsaved = (data: any) => api.post('/sync-tasks/preview', data)
export const testSyncTaskConnection = (data: { datasource_id: number; table?: string }) =>
  api.post('/sync-tasks/test-connection', data)
export const runSyncTask = (_id: number) => Promise.reject(new Error('已废弃：请通过工作流运行数据同步任务'))
export const publishSyncTaskAsWorkflow = (id: number) => api.post(`/sync-tasks/${id}/publish-as-workflow`)

// Alert Rules (监控规则)
export const getAlertRules = () => api.get('/alert-rules')
export const createAlertRule = (data: any) => api.post('/alert-rules', data)
export const updateAlertRule = (id: number, data: any) => api.put(`/alert-rules/${id}`, data)
export const deleteAlertRule = (id: number) => api.delete(`/alert-rules/${id}`)
export const toggleAlertRule = (id: number) => api.patch(`/alert-rules/${id}/toggle`)
export const testAlertNotify = (data: { notify_type?: string; notify_config?: any; channel_id?: number; channel_ids?: number[] }) =>
  api.post('/alert-rules/test-notify', data)

// Word Roots (词根管理)
export const getWordRoots = (params?: any) => api.get('/word-roots', { params })
export const createWordRoot = (data: any) => api.post('/word-roots', data)
export const updateWordRoot = (id: number, data: any) => api.put(`/word-roots/${id}`, data)
export const deleteWordRoot = (id: number) => api.delete(`/word-roots/${id}`)
export const importWordRoots = (file: File) => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/word-roots/import', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
}
export const suggestNaming = (q: string) => api.get('/word-roots/suggest', { params: { q } })

// Metadata (数据资产)
export const getMetadataStats = () => api.get('/metadata/stats')
export const getMetadataLineage = () => api.get('/metadata/lineage')

// Lineage v2 (血缘)
export const getLineageEntities = (type: string) =>
  api.get('/metadata/lineage/entities', { params: { type } })
export const getLineageGraph = (
  entityType: string, entityId: string | number,
  params?: { depth?: number; field_level?: boolean }
) => api.get(`/metadata/lineage/${entityType}/${entityId}`, { params })
export const refreshLineage = () => api.post('/metadata/lineage/refresh')

// Projects (同步任务分组)
export const getProjects = (params?: any) => api.get('/projects', { params })
export const getProject = (id: number) => api.get(`/projects/${id}`)
export const createProject = (data: any) => api.post('/projects', data)
export const updateProject = (id: number, data: any) => api.put(`/projects/${id}`, data)
export const deleteProject = (id: number, moveTo?: number) =>
  api.delete(`/projects/${id}`, { params: moveTo !== undefined ? { move_to: moveTo } : {} })

// DolphinScheduler 代理
export const getDSWorkflows = (params?: any) => api.get('/ds/workflows', { params })
export const runDSWorkflow = (code: number) => api.post(`/ds/workflows/${code}/run`)
export const onlineDSWorkflow = (code: number) => api.post(`/ds/workflows/${code}/online`)
export const offlineDSWorkflow = (code: number) => api.post(`/ds/workflows/${code}/offline`)
export const rerunDSWorkflow = (code: number) => api.post(`/ds/workflows/${code}/rerun`)
export const complementDSWorkflow = (code: number, startDate: string, endDate: string, startParams?: string) => {
  let url = `/ds/workflows/${code}/complement?start_date=${startDate}&end_date=${endDate}`
  if (startParams) url += `&start_params=${encodeURIComponent(startParams)}`
  return api.post(url)
}
export const getDSInstances = (params?: any) => api.get('/ds/instances', { params })
export const getDSCalendar = (days?: number) => api.get('/ds/instances/calendar', { params: { days } })
export const getDSInstanceTasks = (instanceId: number) => api.get(`/ds/instances/${instanceId}/tasks`)
export const getDSTaskLog = (taskId: number) => api.get(`/ds/tasks/${taskId}/log`)
export const rerunDSInstance = (instanceId: number) => api.post(`/ds/instances/${instanceId}/rerun`)
export const getDSMonitor = () => api.get('/ds/monitor')

// System
export const getSystemServices = () => api.get('/system/services')

// Metadata (元数据简版表)
export const getMetadataTables = (datasource_id: number, keyword?: string, limit = 100) =>
  api.get('/metadata/tables', { params: { datasource_id, keyword, limit } })
export const getMetadataColumns = (datasource_id: number, table: string) => api.get('/metadata/columns', { params: { datasource_id, table } })
export const getMetadataPreview = (datasource_id: number, table: string, limit = 10) => api.get('/metadata/preview', { params: { datasource_id, table, limit } })
export const getMetadataQuality = (datasource_id: number, table: string) => api.get('/metadata/quality', { params: { datasource_id, table } })
export const generateDDL = (data: { datasource_id: number; target_table: string; columns: any[] }) =>
  api.post('/metadata/generate-ddl', data)
export const executeDDL = (data: { datasource_id: number; ddl: string }) =>
  api.post('/metadata/execute-ddl', data)

// Notifications
export const getNotifications = (params?: any) => api.get('/notifications', { params })
export const getUnreadCount = () => api.get('/notifications/unread-count')
export const markNotifRead = (id: number) => api.put(`/notifications/${id}/read`)
export const markAllRead = () => api.put('/notifications/read-all')

// Component Folders
export const getComponentFolders = (type?: string) =>
  api.get('/components/folders', { params: type ? { type } : {} })
export const createComponentFolder = (data: { name: string; type: string; parent_id?: number | null }) =>
  api.post('/components/folders', data)
export const renameComponentFolder = (id: number, name: string) =>
  api.put(`/components/folders/${id}`, { name })
export const deleteComponentFolder = (id: number) =>
  api.delete(`/components/folders/${id}`)

// Components
export const getComponents = (params?: any) => api.get('/components', { params })
export const getComponent = (id: number) => api.get(`/components/${id}`)
export const createComponent = (data: any) => api.post('/components', data)
export const updateComponent = (id: number, data: any) => api.put(`/components/${id}`, data)
export const deleteComponent = (id: number) => api.delete(`/components/${id}`)
export const testComponent = (id: number) => api.post(`/components/${id}/test`)
export const publishComponent = (id: number) => api.post(`/components/${id}/publish`)
export const offlineComponent = (id: number) => api.post(`/components/${id}/offline`)
export const runComponent = (id: number) => api.post(`/components/${id}/run`)
export const runSqlAdhoc = (data: { datasource_id: number; sql: string }) =>
  api.post('/components/run-sql', data, { timeout: 60000 })
export const runComponentScript = (id: number, datasourceId?: number) =>
  api.post(`/components/${id}/run${datasourceId ? `?datasource_id=${datasourceId}` : ''}`, {}, { timeout: 120000 })
export const quickPublishComponent = (id: number) =>
  api.post(`/components/${id}/quick-publish`)
export const setComponentStatus = (id: number, status: string) =>
  api.put(`/components/${id}/status`, { status })
// Component Move / Reorder
export const moveComponent = (id: number, folderId?: number | null, sortOrder?: number) =>
  api.put(`/components/${id}/move`, { folder_id: folderId ?? 0, sort_order: sortOrder })
export const reorderComponents = (orders: { id: number; sort_order: number }[]) =>
  api.post('/components/reorder', { orders })
export const moveComponentFolder = (id: number, parentId?: number | null, sortOrder?: number) =>
  api.put(`/components/folders/${id}/move`, { parent_id: parentId ?? 0, sort_order: sortOrder })
export const resumeComponent = (id: number) =>
  api.post(`/components/${id}/resume`)

// Admin — 用户/角色/权限/SSO/通知配置
export const adminListUsers = (params?: any) => api.get('/admin/users', { params })
export const adminCreateUser = (data: any) => api.post('/admin/users', data)
export const adminUpdateUser = (id: number, data: any) => api.put(`/admin/users/${id}`, data)
export const adminDeleteUser = (id: number) => api.delete(`/admin/users/${id}`)

export const adminListRoles = () => api.get('/admin/roles')
export const adminCreateRole = (data: any) => api.post('/admin/roles', data)
export const adminUpdateRole = (id: number, data: any) => api.put(`/admin/roles/${id}`, data)
export const adminDeleteRole = (id: number) => api.delete(`/admin/roles/${id}`)

export const adminListPermissions = () => api.get('/admin/permissions')

export const adminListSso = () => api.get('/admin/sso')
export const adminUpdateSso = (provider: string, data: any) => api.put(`/admin/sso/${provider}`, data)
export const adminGetSsoPublic = () => api.get('/admin/sso/public')

export const adminGetConfig = (key: string) => api.get(`/admin/config/${key}`)
export const adminSetConfig = (key: string, data: any) => api.put(`/admin/config/${key}`, data)
export const adminTestSmtp = () => api.post('/admin/config/smtp/test')

// Admin — 资源级 ACL
export const adminListResourceAccess = (resource_type: string, resource_id: number) =>
  api.get('/admin/resource-access', { params: { resource_type, resource_id } })
export const adminGrantResourceAccess = (data: {
  resource_type: string; resource_id: number
  subject_type: string; subject_id: number; permission: string
}) => api.post('/admin/resource-access', data)
export const adminRevokeResourceAccess = (data: {
  resource_type: string; resource_id: number
  subject_type: string; subject_id: number
}) => api.delete('/admin/resource-access', { data })

// Workflows
export const getWorkflows = (params?: any) => api.get('/workflows', { params })
export const getWorkflow = (id: number) => api.get(`/workflows/${id}`)
export const createWorkflow = (data: any) => api.post('/workflows', data)
export const updateWorkflow = (id: number, data: any) => api.put(`/workflows/${id}`, data)
export const deleteWorkflow = (id: number) => api.delete(`/workflows/${id}`)
export const testWorkflow = (id: number) => api.post(`/workflows/${id}/test`)
export const publishWorkflow = (id: number) => api.post(`/workflows/${id}/publish`)
export const offlineWorkflow = (id: number) => api.post(`/workflows/${id}/offline`)
export const runWorkflow = (id: number, params?: Record<string, string>) => api.post(`/workflows/${id}/run`, { params })
export const scheduleWorkflowOnline = (id: number) => api.post(`/workflows/${id}/schedule/online`)
export const scheduleWorkflowOffline = (id: number) => api.post(`/workflows/${id}/schedule/offline`)
export const cronPreview = (cron_expression: string) => api.post('/workflows/cron-preview', { cron_expression })
export const getScheduledWorkflows = () => api.get('/workflows/scheduled')
export const getWorkflowVersions = (id: number) => api.get(`/workflows/${id}/versions`)
export const getWorkflowVersion = (id: number, verId: number) => api.get(`/workflows/${id}/versions/${verId}`)
export const rollbackWorkflowVersion = (id: number, verId: number) => api.post(`/workflows/${id}/versions/${verId}/rollback`)

// Transfer (Import/Export)
export const exportComponents = (ids: number[]) =>
  api.post('/transfer/export/components', { ids })
export const exportWorkflows = (ids: number[]) =>
  api.post('/transfer/export/workflows', { ids })
export const importBundle = (file: File, strategy: string = 'skip') => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post(`/transfer/import?strategy=${strategy}`, fd)
}
export const previewComponentExport = (id: number) =>
  api.get(`/transfer/export/components/${id}/preview`)

// Notify Channels
export const adminListChannels = () => api.get('/admin/notify-channels')
export const adminCreateChannel = (data: any) => api.post('/admin/notify-channels', data)
export const adminUpdateChannel = (id: number, data: any) => api.put(`/admin/notify-channels/${id}`, data)
export const adminDeleteChannel = (id: number) => api.delete(`/admin/notify-channels/${id}`)
export const adminTestChannel = (id: number) => api.post(`/admin/notify-channels/${id}/test`)

export default api
