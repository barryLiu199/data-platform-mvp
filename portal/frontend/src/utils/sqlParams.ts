/**
 * SQL 参数提取、替换、合并 — 统一工具模块
 * 消除 SqlParamModal / SqlDev 中的重复逻辑
 */

// ---- 常量 ----

export const QUOTED_TYPES = ['VARCHAR', 'DATE', 'TIME', 'TIMESTAMP'] as const
export const DEFAULT_PARAM_TYPE = 'VARCHAR'
export const PARAM_TYPES = [
  'VARCHAR', 'INTEGER', 'LONG', 'FLOAT', 'DOUBLE', 'DATE', 'TIME', 'TIMESTAMP',
] as const

// ---- 类型 ----

export interface ParamDef {
  prop: string
  type: string
  value: string
  direct: string
}

// ---- 函数 ----

/**
 * 从 SQL 中提取 ${xxx} 参数名（排除注释内的），按出现顺序返回，去重
 */
export function extractSqlParams(sql: string): string[] {
  const cleaned = sql
    .replace(/--.*$/gm, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
  const matches = cleaned.matchAll(/\$\{(\w+)\}/g)
  const seen = new Set<string>()
  const result: string[] = []
  for (const m of matches) {
    if (!seen.has(m[1])) {
      seen.add(m[1])
      result.push(m[1])
    }
  }
  return result
}

/**
 * 合并 SQL 中发现的参数和已定义的 localParams
 * 按 SQL 中出现顺序排列，未在 SQL 中出现但已定义的 IN 参数追加在后
 */
export function mergeParams(
  sqlParamNames: string[],
  localParams: Array<{ prop: string; type: string; value: string; direct: string }>,
): ParamDef[] {
  const defMap = new Map<string, { type: string; value: string; direct: string }>()
  for (const p of (localParams || [])) {
    if (p.prop) defMap.set(p.prop, { type: p.type, value: p.value, direct: p.direct })
  }

  const result: ParamDef[] = []
  const seen = new Set<string>()

  for (const name of sqlParamNames) {
    const def = defMap.get(name)
    result.push({
      prop: name,
      type: def?.type || DEFAULT_PARAM_TYPE,
      value: def?.value || '',
      direct: def?.direct || 'IN',
    })
    seen.add(name)
  }

  for (const p of (localParams || [])) {
    if (p.prop && !seen.has(p.prop) && p.direct === 'IN') {
      result.push({ prop: p.prop, type: p.type, value: p.value, direct: p.direct })
    }
  }

  return result
}

/**
 * 替换 SQL 中的 ${param_name}，根据类型自动处理引号
 * 先处理用户已手动加引号的 '${xxx}'，再处理裸 ${xxx}，避免双引号
 */
export function substituteSqlParams(
  sql: string,
  values: Record<string, string>,
  typeMap: Map<string, string>,
): string {
  let s = sql
  for (const [key, val] of Object.entries(values)) {
    const pType = typeMap.get(key) || DEFAULT_PARAM_TYPE
    const needsQuote = (QUOTED_TYPES as readonly string[]).includes(pType)
    const quotedVal = needsQuote ? `'${val}'` : val
    s = s.split("'${" + key + "}'").join(quotedVal)
    s = s.split('${' + key + '}').join(quotedVal)
  }
  return s
}
