<template>
  <div ref="editorContainer" class="code-editor" :style="{ height: height }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import { format as sqlFormat } from 'sql-formatter'
import { getMetadataTables, getMetadataColumns } from '../api'

;(self as any).MonacoEnvironment = {
  getWorker() { return new editorWorker() },
}

const props = withDefaults(defineProps<{
  modelValue: string
  language?: string
  readonly?: boolean
  height?: string
  datasourceId?: number
}>(), {
  language: 'sql',
  readonly: false,
  height: '320px',
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const editorContainer = ref<HTMLElement | null>(null)
let editor: monaco.editor.IStandaloneCodeEditor | null = null
let suppressEmit = false

// ─── SQL 智能补全 ──────────────────────────────────────────────────────────────
// 模块级缓存：多个 CodeEditor 实例共享
const _tableCache = new Map<number, { name: string; comment: string }[]>()
const _colCache   = new Map<string,  { name: string; type: string; comment: string; pk: boolean }[]>()
// modelUri → datasourceId，供 completion provider 查询
const _uriDsMap   = new Map<string, number>()
let   _providerDisposable: monaco.IDisposable | null = null

const SQL_KEYWORDS = [
  'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'AS', 'ON',
  'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 'FULL OUTER JOIN', 'CROSS JOIN',
  'GROUP BY', 'ORDER BY', 'HAVING', 'LIMIT', 'OFFSET',
  'UNION', 'UNION ALL', 'INTERSECT', 'EXCEPT',
  'INSERT INTO', 'VALUES', 'UPDATE', 'SET', 'DELETE FROM',
  'CREATE TABLE', 'DROP TABLE', 'ALTER TABLE', 'ADD COLUMN', 'DROP COLUMN',
  'IN', 'NOT IN', 'LIKE', 'NOT LIKE', 'BETWEEN', 'IS NULL', 'IS NOT NULL', 'EXISTS',
  'DISTINCT', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'WITH',
  'ASC', 'DESC', 'NULL', 'TRUE', 'FALSE',
  'PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE', 'INDEX',
  'VARCHAR', 'CHAR', 'TEXT', 'INT', 'BIGINT', 'SMALLINT', 'TINYINT',
  'FLOAT', 'DOUBLE', 'DECIMAL', 'BOOLEAN', 'DATE', 'DATETIME', 'TIMESTAMP',
]

const SQL_FUNCTIONS: { name: string; snippet: string; detail: string }[] = [
  // 聚合
  { name: 'COUNT',    snippet: 'COUNT($1)',        detail: '计数' },
  { name: 'SUM',      snippet: 'SUM($1)',           detail: '求和' },
  { name: 'AVG',      snippet: 'AVG($1)',           detail: '平均值' },
  { name: 'MAX',      snippet: 'MAX($1)',           detail: '最大值' },
  { name: 'MIN',      snippet: 'MIN($1)',           detail: '最小值' },
  { name: 'GROUP_CONCAT', snippet: 'GROUP_CONCAT($1)', detail: '分组拼接' },
  // 条件
  { name: 'IF',       snippet: 'IF($1, $2, $3)',    detail: '条件判断' },
  { name: 'IFNULL',   snippet: 'IFNULL($1, $2)',    detail: '空值替换' },
  { name: 'COALESCE', snippet: 'COALESCE($1, $2)',  detail: '取第一个非空' },
  { name: 'NULLIF',   snippet: 'NULLIF($1, $2)',    detail: '相等则返回 NULL' },
  // 字符串
  { name: 'CONCAT',     snippet: 'CONCAT($1, $2)',         detail: '字符串拼接' },
  { name: 'CONCAT_WS',  snippet: "CONCAT_WS('$1', $2)",    detail: '带分隔符拼接' },
  { name: 'SUBSTRING',  snippet: 'SUBSTRING($1, $2, $3)',   detail: '截取子串' },
  { name: 'TRIM',       snippet: 'TRIM($1)',                detail: '去首尾空格' },
  { name: 'UPPER',      snippet: 'UPPER($1)',               detail: '转大写' },
  { name: 'LOWER',      snippet: 'LOWER($1)',               detail: '转小写' },
  { name: 'LENGTH',     snippet: 'LENGTH($1)',              detail: '字节长度' },
  { name: 'CHAR_LENGTH',snippet: 'CHAR_LENGTH($1)',         detail: '字符长度' },
  { name: 'REPLACE',    snippet: 'REPLACE($1, $2, $3)',     detail: '字符串替换' },
  { name: 'LPAD',       snippet: 'LPAD($1, $2, $3)',        detail: '左填充' },
  { name: 'RPAD',       snippet: 'RPAD($1, $2, $3)',        detail: '右填充' },
  // 日期
  { name: 'NOW',          snippet: 'NOW()',                              detail: '当前日期时间' },
  { name: 'CURDATE',      snippet: 'CURDATE()',                          detail: '当前日期' },
  { name: 'DATE_FORMAT',  snippet: "DATE_FORMAT($1, '%Y-%m-%d')",        detail: '日期格式化' },
  { name: 'DATE_ADD',     snippet: 'DATE_ADD($1, INTERVAL $2 DAY)',      detail: '日期加法' },
  { name: 'DATE_SUB',     snippet: 'DATE_SUB($1, INTERVAL $2 DAY)',      detail: '日期减法' },
  { name: 'DATEDIFF',     snippet: 'DATEDIFF($1, $2)',                   detail: '日期差（天）' },
  { name: 'TIMESTAMPDIFF',snippet: 'TIMESTAMPDIFF(DAY, $1, $2)',         detail: '时间差' },
  { name: 'YEAR',    snippet: 'YEAR($1)',    detail: '年份' },
  { name: 'MONTH',   snippet: 'MONTH($1)',   detail: '月份' },
  { name: 'DAY',     snippet: 'DAY($1)',     detail: '日' },
  { name: 'QUARTER', snippet: 'QUARTER($1)', detail: '季度' },
  { name: 'WEEK',    snippet: 'WEEK($1)',    detail: '周数' },
  // 数值
  { name: 'ROUND', snippet: 'ROUND($1, $2)', detail: '四舍五入' },
  { name: 'FLOOR', snippet: 'FLOOR($1)',     detail: '向下取整' },
  { name: 'CEIL',  snippet: 'CEIL($1)',      detail: '向上取整' },
  { name: 'ABS',   snippet: 'ABS($1)',       detail: '绝对值' },
  { name: 'MOD',   snippet: 'MOD($1, $2)',   detail: '取余' },
  // 转换
  { name: 'CAST',    snippet: 'CAST($1 AS $2)',      detail: '类型转换' },
  { name: 'CONVERT', snippet: 'CONVERT($1, $2)',     detail: '类型转换' },
  // 窗口函数
  { name: 'ROW_NUMBER',  snippet: 'ROW_NUMBER() OVER (PARTITION BY $1 ORDER BY $2)', detail: '行号' },
  { name: 'RANK',        snippet: 'RANK() OVER (PARTITION BY $1 ORDER BY $2)',       detail: '排名（跳号）' },
  { name: 'DENSE_RANK',  snippet: 'DENSE_RANK() OVER (PARTITION BY $1 ORDER BY $2)',detail: '排名（不跳号）' },
  { name: 'LAG',         snippet: 'LAG($1, 1) OVER (ORDER BY $2)',                  detail: '前 N 行值' },
  { name: 'LEAD',        snippet: 'LEAD($1, 1) OVER (ORDER BY $2)',                 detail: '后 N 行值' },
  { name: 'FIRST_VALUE', snippet: 'FIRST_VALUE($1) OVER (PARTITION BY $2 ORDER BY $3)', detail: '窗口第一个值' },
  { name: 'LAST_VALUE',  snippet: 'LAST_VALUE($1) OVER (PARTITION BY $2 ORDER BY $3)',  detail: '窗口最后一个值' },
]

async function _fetchTables(dsId: number) {
  if (_tableCache.has(dsId)) return _tableCache.get(dsId)!
  try {
    const res: any = await getMetadataTables(dsId, undefined, 500)
    const list = (res?.tables || []).map((t: any) => ({
      name: t.name as string,
      comment: (t.comment as string) || '',
    }))
    _tableCache.set(dsId, list)
    return list
  } catch { return [] }
}

async function _fetchColumns(dsId: number, table: string) {
  const key = `${dsId}:${table}`
  if (_colCache.has(key)) return _colCache.get(key)!
  try {
    const res: any = await getMetadataColumns(dsId, table)
    const list = (res?.columns || []).map((c: any) => ({
      name:    c.name    as string,
      type:    c.type    as string || '',
      comment: c.comment as string || '',
      pk:      !!c.primary_key,
    }))
    _colCache.set(key, list)
    return list
  } catch { return [] }
}

function _ensureProvider() {
  if (_providerDisposable) return
  _providerDisposable = monaco.languages.registerCompletionItemProvider('sql', {
    triggerCharacters: [' ', '.', '('],
    async provideCompletionItems(model, position) {
      const dsId = _uriDsMap.get(model.uri.toString())
      const textBefore = model.getValueInRange({
        startLineNumber: 1, startColumn: 1,
        endLineNumber: position.lineNumber, endColumn: position.column,
      })
      const word = model.getWordUntilPosition(position)
      const range = {
        startLineNumber: position.lineNumber,
        endLineNumber:   position.lineNumber,
        startColumn:     word.startColumn,
        endColumn:       word.endColumn,
      }

      // ① 点号后 → 列名  (t_user.xxx)
      const dotMatch = textBefore.match(/\b(\w+)\.\w*$/)
      if (dotMatch && dsId) {
        const cols = await _fetchColumns(dsId, dotMatch[1])
        if (cols.length) {
          return {
            suggestions: cols.map((c: any, i: any) => ({
              label: {
                label:       c.name,
                detail:      c.type ? `  ${c.type}` : '',
                description: (c.pk ? '🔑 ' : '') + (c.comment || ''),
              },
              kind:       monaco.languages.CompletionItemKind.Field,
              insertText: c.name,
              range,
              sortText:   String(i).padStart(4, '0'),
            }))
          }
        }
      }

      // ② FROM / JOIN / INTO / UPDATE / TABLE 后 → 表名
      const inTableCtx = /\b(FROM|JOIN|UPDATE\s+|INTO\s+|TABLE\s+)\s*\w*$/i.test(textBefore)
      if (inTableCtx && dsId) {
        const tables = await _fetchTables(dsId)
        if (tables.length) {
          return {
            suggestions: tables.map((t: any, i: any) => ({
              label: { label: t.name, description: t.comment },
              kind:       monaco.languages.CompletionItemKind.Module,
              insertText: t.name,
              range,
              sortText:   String(i).padStart(4, '0'),
            }))
          }
        }
      }

      // ③ 默认：关键字 + 函数 + 表名（有 datasource 时追加）
      const suggestions: monaco.languages.CompletionItem[] = []

      SQL_KEYWORDS.forEach(kw => suggestions.push({
        label:      kw,
        kind:       monaco.languages.CompletionItemKind.Keyword,
        insertText: kw,
        range,
        sortText:   '1' + kw,
      }))

      SQL_FUNCTIONS.forEach(fn => suggestions.push({
        label:      { label: fn.name, description: fn.detail },
        kind:       monaco.languages.CompletionItemKind.Function,
        insertText: fn.snippet,
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
        range,
        sortText:   '2' + fn.name,
      }))

      if (dsId) {
        const tables = await _fetchTables(dsId)
        tables.forEach((t: any) => suggestions.push({
          label:      { label: t.name, description: t.comment },
          kind:       monaco.languages.CompletionItemKind.Module,
          insertText: t.name,
          range,
          sortText:   '3' + t.name,
        }))
      }

      return { suggestions }
    },
  })
}

// ─── Editor ───────────────────────────────────────────────────────────────────
onMounted(() => {
  if (!editorContainer.value) return
  editor = monaco.editor.create(editorContainer.value, {
    value:               props.modelValue || '',
    language:            props.language,
    theme:               'vs',
    automaticLayout:     true,
    fontSize:            13,
    minimap:             { enabled: false },
    readOnly:            props.readonly,
    scrollBeyondLastLine:false,
    tabSize:             2,
    wordWrap:            'on',
    fontFamily:          "'JetBrains Mono', Consolas, 'Courier New', monospace",
    // 补全相关配置
    suggestOnTriggerCharacters: true,
    quickSuggestions: { other: true, comments: false, strings: false },
    acceptSuggestionOnEnter:    'on',
    suggest: { showIcons: true, showStatusBar: true, insertMode: 'replace' },
  })

  editor.onDidChangeModelContent(() => {
    if (suppressEmit) return
    emit('update:modelValue', editor!.getValue())
  })

  // 注册 SQL 补全（全局只注册一次）
  if (props.language === 'sql') _ensureProvider()

  // 绑定 uri → datasourceId
  const uri = editor.getModel()?.uri.toString()
  if (uri && props.datasourceId) _uriDsMap.set(uri, props.datasourceId)
})

watch(() => props.datasourceId, (dsId) => {
  const uri = editor?.getModel()?.uri.toString()
  if (!uri) return
  if (dsId) _uriDsMap.set(uri, dsId)
  else       _uriDsMap.delete(uri)
})

watch(() => props.modelValue, (v) => {
  if (editor && v !== editor.getValue()) {
    suppressEmit = true
    editor.setValue(v || '')
    suppressEmit = false
  }
})

watch(() => props.language, (lang) => {
  if (!editor || !lang) return
  const model = editor.getModel()
  if (model) monaco.editor.setModelLanguage(model, lang)
  if (lang === 'sql') _ensureProvider()
})

watch(() => props.readonly, (ro) => {
  editor?.updateOptions({ readOnly: ro })
})

onBeforeUnmount(() => {
  const uri = editor?.getModel()?.uri.toString()
  if (uri) _uriDsMap.delete(uri)
  editor?.dispose()
  editor = null
})

function getSelectedText(): string {
  if (!editor) return ''
  const sel = editor.getSelection()
  if (!sel || sel.isEmpty()) return ''
  return editor.getModel()?.getValueInRange(sel) ?? ''
}

function formatDocument(): void {
  if (!editor) return
  const value = editor.getValue()
  if (!value.trim()) return
  try {
    const formatted = sqlFormat(value, {
      language: 'mysql',
      tabWidth: 2,
      keywordCase: 'upper',
      linesBetweenQueries: 2,
    })
    suppressEmit = true
    editor.setValue(formatted)
    suppressEmit = false
    emit('update:modelValue', formatted)
  } catch {
    // 格式化失败则静默忽略
  }
}

defineExpose({ getSelectedText, formatDocument })
</script>

<style scoped>
.code-editor {
  width: 100%;
  border: 1px solid #E5E8ED;
  border-radius: 6px;
  overflow: hidden;
}
</style>
