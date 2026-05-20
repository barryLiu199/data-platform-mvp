<script setup lang="ts">
import { ref, computed, watch } from 'vue'

export interface ParamDef {
  prop: string
  type: string
  value: string
  direct?: string
}

const props = defineProps<{
  visible: boolean
  params: ParamDef[]
  sql: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'confirm', values: Record<string, string>): void
}>()

// 内部可编辑副本
const localValues = ref<Record<string, string>>({})

watch(() => props.visible, (v) => {
  if (v) {
    // 初始化：优先用 localStorage 记忆值 → 再用默认值
    const stored = _loadStored()
    const vals: Record<string, string> = {}
    for (const p of props.params) {
      if (stored[p.prop] !== undefined) {
        vals[p.prop] = stored[p.prop]
      } else if (p.value) {
        vals[p.prop] = p.value
      } else if (p.type === 'DATE') {
        // 默认 T-1
        vals[p.prop] = _yesterday()
      } else if (p.type === 'TIMESTAMP') {
        vals[p.prop] = _yesterday() + ' 00:00:00'
      } else if (p.type === 'INTEGER' || p.type === 'LONG') {
        vals[p.prop] = '0'
      } else if (p.type === 'FLOAT' || p.type === 'DOUBLE') {
        vals[p.prop] = '0.0'
      } else {
        vals[p.prop] = ''
      }
    }
    localValues.value = vals
  }
})

// 预览替换后的 SQL
const previewSql = computed(() => {
  let s = props.sql
  for (const p of props.params) {
    const val = localValues.value[p.prop] ?? ''
    // 全局替换 ${param_name}
    s = s.split('${' + p.prop + '}').join(val)
  }
  return s
})

const showPreview = ref(false)

// 日期快捷按钮
function setDateShortcut(paramName: string, type: 'T-1' | 'T' | 'weekStart' | 'monthStart') {
  const now = new Date()
  let d: Date
  switch (type) {
    case 'T-1':
      d = new Date(now); d.setDate(d.getDate() - 1); break
    case 'T':
      d = now; break
    case 'weekStart':
      d = new Date(now)
      const day = d.getDay() || 7
      d.setDate(d.getDate() - day + 1)
      break
    case 'monthStart':
      d = new Date(now.getFullYear(), now.getMonth(), 1); break
  }
  localValues.value[paramName] = _formatDate(d)
}

function handleConfirm() {
  // 持久化到 localStorage
  _saveStored(localValues.value)
  emit('confirm', { ...localValues.value })
  emit('update:visible', false)
}

function handleCancel() {
  emit('update:visible', false)
}

// --- localStorage 工具 ---
const STORAGE_KEY = 'sql_param_values'

function _loadStored(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch { return {} }
}

function _saveStored(vals: Record<string, string>) {
  try {
    const existing = _loadStored()
    Object.assign(existing, vals)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(existing))
  } catch {}
}

function _yesterday(): string {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  return _formatDate(d)
}

function _formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
</script>

<template>
  <a-modal
    :visible="visible"
    title="运行参数"
    :width="560"
    :mask-closable="false"
    @cancel="handleCancel"
    @ok="handleConfirm"
    ok-text="执行"
    cancel-text="取消"
    unmount-on-close
  >
    <!-- 示例提示 -->
    <div class="param-example">
      <div class="param-example__title">使用示例</div>
      <code class="param-example__code">SELECT * FROM orders WHERE dt = '${'{'}bizdate{'}'}' AND type = ${'{'}type{'}'}</code>
      <div class="param-example__tip">日期/字符串类型请在 SQL 中用引号包裹，如 <code>'${'{'}bizdate{'}'}'</code></div>
    </div>

    <!-- 参数列表 -->
    <div class="param-list">
      <div v-for="p in params" :key="p.prop" class="param-item">
        <div class="param-item__label">
          <span class="param-item__name">{{ p.prop }}</span>
          <a-tag size="small" :color="p.type === 'DATE' || p.type === 'TIMESTAMP' ? 'blue' : p.type === 'INTEGER' || p.type === 'LONG' ? 'green' : p.type === 'FLOAT' || p.type === 'DOUBLE' ? 'orange' : 'gray'">
            {{ p.type }}
          </a-tag>
        </div>

        <div class="param-item__input">
          <!-- DATE -->
          <template v-if="p.type === 'DATE'">
            <a-date-picker
              v-model="localValues[p.prop]"
              style="width: 100%"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
            />
            <div class="date-shortcuts">
              <a-tag size="small" checkable @check="setDateShortcut(p.prop, 'T-1')">T-1 昨天</a-tag>
              <a-tag size="small" checkable @check="setDateShortcut(p.prop, 'T')">T 今天</a-tag>
              <a-tag size="small" checkable @check="setDateShortcut(p.prop, 'weekStart')">本周一</a-tag>
              <a-tag size="small" checkable @check="setDateShortcut(p.prop, 'monthStart')">月初</a-tag>
            </div>
          </template>

          <!-- TIMESTAMP -->
          <template v-else-if="p.type === 'TIMESTAMP' || p.type === 'TIME'">
            <a-date-picker
              v-model="localValues[p.prop]"
              style="width: 100%"
              show-time
              format="YYYY-MM-DD HH:mm:ss"
              value-format="YYYY-MM-DD HH:mm:ss"
            />
          </template>

          <!-- INTEGER / LONG -->
          <template v-else-if="p.type === 'INTEGER' || p.type === 'LONG'">
            <a-input-number
              v-model="localValues[p.prop]"
              style="width: 100%"
              :precision="0"
              placeholder="请输入整数"
            />
          </template>

          <!-- FLOAT / DOUBLE -->
          <template v-else-if="p.type === 'FLOAT' || p.type === 'DOUBLE'">
            <a-input-number
              v-model="localValues[p.prop]"
              style="width: 100%"
              :precision="4"
              placeholder="请输入数值"
            />
          </template>

          <!-- VARCHAR / 默认 -->
          <template v-else>
            <a-input
              v-model="localValues[p.prop]"
              placeholder="请输入值"
              allow-clear
            />
          </template>
        </div>
      </div>
    </div>

    <!-- 预览替换后 SQL -->
    <div class="param-preview">
      <div class="param-preview__toggle" @click="showPreview = !showPreview">
        <span>{{ showPreview ? '▼' : '▶' }} 预览替换后 SQL</span>
      </div>
      <div v-if="showPreview" class="param-preview__code">
        <pre>{{ previewSql }}</pre>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.param-example {
  padding: 12px 14px;
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  font-size: var(--font-size-xs);
  line-height: 1.6;
}
.param-example__title {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: 4px;
}
.param-example__code {
  display: block;
  padding: 6px 10px;
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-family: var(--font-family-mono);
  font-size: 11px;
  color: var(--color-primary);
  white-space: pre-wrap;
  word-break: break-all;
  margin: 6px 0;
}
.param-example__tip {
  color: var(--color-text-tertiary);
  font-size: 11px;
}
.param-example__tip code {
  background: var(--color-bg-base);
  padding: 1px 4px;
  border-radius: 3px;
  font-family: var(--font-family-mono);
  font-size: 11px;
}

.param-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.param-item__label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.param-item__name {
  font-weight: var(--font-weight-medium);
  font-family: var(--font-family-mono);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}
.param-item__input {
  width: 100%;
}

.date-shortcuts {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}

.param-preview {
  margin-top: 16px;
  border-top: 1px solid var(--color-border-subtle);
  padding-top: 12px;
}
.param-preview__toggle {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
  user-select: none;
}
.param-preview__toggle:hover {
  color: var(--color-primary);
}
.param-preview__code {
  margin-top: 8px;
  max-height: 200px;
  overflow: auto;
}
.param-preview__code pre {
  margin: 0;
  padding: 10px 12px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-family: var(--font-family-mono);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--color-text-primary);
}
</style>
