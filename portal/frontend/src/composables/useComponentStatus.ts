// ── 组件状态系统 ─────────────────────────────────────────────────────────
// 纯函数/常量，无响应式状态

export const STATUS_DEFS: Record<string, { label: string; color: string; manual: boolean }> = {
  draft:       { label: '草稿',   color: '#86909C', manual: false },
  developing:  { label: '开发中', color: '#2B5AED', manual: true  },
  testing:     { label: '测试中', color: '#FF7D00', manual: true  },
  reviewing:   { label: '审核中', color: '#14B8A6', manual: true  },
  tested:      { label: '已测试', color: '#A3C644', manual: true  },
  online:      { label: '已上线', color: '#00B42A', manual: false },
  offline:     { label: '已下线', color: '#C9CDD4', manual: true  },
  paused:      { label: '已暂停', color: '#F53F3F', manual: true  },
  deprecated:  { label: '已废弃', color: '#6B7280', manual: true  },
  archived:    { label: '已归档', color: '#722ED1', manual: true  },
}

export const STATUS_TRANSITIONS: Record<string, string[]> = {
  draft:      ['developing', 'testing', 'deprecated', 'archived'],
  developing: ['testing', 'paused', 'deprecated'],
  testing:    ['reviewing', 'tested', 'paused', 'deprecated'],
  reviewing:  ['tested', 'paused', 'developing'],
  tested:     ['paused', 'testing'],
  online:     ['offline', 'paused'],
  offline:    ['online', 'archived', 'paused', 'developing'],
  paused:     [],
  deprecated: ['archived'],
  archived:   [],
}

export function statusLabel(s: string): string {
  return STATUS_DEFS[s]?.label || s
}

export function statusColor(s: string): string {
  return STATUS_DEFS[s]?.color || '#86909C'
}

export function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.substring(0, 2), 16)
  const g = parseInt(h.substring(2, 4), 16)
  const b = parseInt(h.substring(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

export function statusTagStyle(s: string) {
  const color = statusColor(s)
  return {
    background: hexToRgba(color, 0.12),
    color: color,
  }
}

export function manualStatusOptions(current: string) {
  if (current === 'paused') return []
  if (current === 'archived') return []
  const allowed = STATUS_TRANSITIONS[current] ?? []
  return allowed
    .filter(k => STATUS_DEFS[k]?.manual)
    .map(k => ({ value: k, label: STATUS_DEFS[k].label, color: STATUS_DEFS[k].color }))
}

/** 可手动编辑的状态集合 */
export const EDITABLE_STATUSES = Object.entries(STATUS_DEFS)
  .filter(([, v]) => v.manual)
  .map(([k]) => k)

/** 可发布的状态集合 */
export const PUBLISHABLE_STATUSES = ['tested', 'offline']
