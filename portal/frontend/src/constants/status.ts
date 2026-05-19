/**
 * 全局状态常量 — 唯一真相源
 * 所有页面的状态颜色、文案统一从这里引用
 */

/* ============================================================
   执行状态 — DolphinScheduler 工作流实例 / 任务实例
   用于：SchedulerHistory, InstanceDetail, SchedulerTasks(实例列)
   ============================================================ */
export const EXECUTION_STATUS = {
  SUCCESS:   { label: '成功',   color: '#16A34A', bg: '#F0FDF4' },
  FAILURE:   { label: '失败',   color: '#DC2626', bg: '#FEF2F2' },
  RUNNING:   { label: '运行中', color: '#2563EB', bg: '#EFF6FF' },
  STOP:      { label: '停止',   color: '#94A3B8', bg: '#F1F5F9' },
  KILL:      { label: '已终止', color: '#F59E0B', bg: '#FFFBEB' },
  SUBMITTED: { label: '已提交', color: '#0EA5E9', bg: '#F0F9FF' },
  PAUSE:     { label: '暂停',   color: '#F59E0B', bg: '#FFFBEB' },
  DELAY:     { label: '延迟',   color: '#8B5CF6', bg: '#F5F3FF' },
  WAIT:      { label: '等待',   color: '#6B7280', bg: '#F9FAFB' },
  NEED_FAULT_TOLERANCE: { label: '容错中', color: '#F59E0B', bg: '#FFFBEB' },
} as const

export type ExecutionStatusKey = keyof typeof EXECUTION_STATUS

export function getExecutionStatus(state: string) {
  return EXECUTION_STATUS[state as ExecutionStatusKey] ?? { label: state, color: '#94A3B8', bg: '#F1F5F9' }
}

/* ============================================================
   生命周期状态 — 工作流 / 组件
   用于：Workflow, Component, SchedulerTasks(工作流状态列)
   ============================================================ */
export const LIFECYCLE_STATUS = {
  draft:   { label: '草稿',   color: '#94A3B8', tagColor: 'gray'   },
  tested:  { label: '已测试', color: '#0EA5E9', tagColor: 'cyan'   },
  online:  { label: '已上线', color: '#16A34A', tagColor: 'green'  },
  offline: { label: '已下线', color: '#F59E0B', tagColor: 'orange' },
} as const

export type LifecycleStatusKey = keyof typeof LIFECYCLE_STATUS

export function getLifecycleStatus(status: string) {
  return LIFECYCLE_STATUS[status as LifecycleStatusKey] ?? { label: status, color: '#94A3B8', tagColor: 'gray' }
}

/* ============================================================
   同步任务状态
   用于：SyncTaskCanvas, SyncTaskWizard
   ============================================================ */
export const SYNC_TASK_STATUS = {
  draft:  { label: '草稿', color: '#94A3B8', tagColor: 'gray'   },
  active: { label: '运行', color: '#16A34A', tagColor: 'green'  },
  paused: { label: '暂停', color: '#F59E0B', tagColor: 'orange' },
  error:  { label: '异常', color: '#DC2626', tagColor: 'red'    },
} as const

export type SyncTaskStatusKey = keyof typeof SYNC_TASK_STATUS

export function getSyncTaskStatus(status: string) {
  return SYNC_TASK_STATUS[status as SyncTaskStatusKey] ?? { label: status, color: '#94A3B8', tagColor: 'gray' }
}

/* ============================================================
   执行结果符号 — 运行历史的简洁标识
   ============================================================ */
export function getRunSymbol(state: string): string {
  switch (state) {
    case 'SUCCESS': return '✓'
    case 'FAILURE': return '✗'
    default: return '●'
  }
}
