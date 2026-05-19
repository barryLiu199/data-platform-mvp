# Design Tokens — 数据中台 MVP

> 定位：专业高效 + 甲方演示品质感
> 风格：优化版蓝白，成熟企业级

---

## 1. 色彩体系

### 主色（Brand）

| Token | 值 | 用途 |
|-------|------|------|
| --color-primary | #2563EB | 主操作按钮、导航激活、链接 |
| --color-primary-hover | #1D4ED8 | 主色悬停态 |
| --color-primary-active | #1E40AF | 主色按下态 |
| --color-primary-light | #EFF6FF | 主色浅底（选中行、标签底色）|
| --color-primary-border | #BFDBFE | 主色浅边框 |

### 辅助色（Accent）

| Token | 值 | 用途 |
|-------|------|------|
| --color-accent | #0EA5E9 | 数据可视化强调、次要操作 |
| --color-accent-light | #F0F9FF | 辅助浅底 |

### 状态色（Status）

| Token | 值 | 语义 |
|-------|------|------|
| --color-success | #16A34A | 成功、已完成、健康 |
| --color-success-light | #F0FDF4 | 成功浅底 |
| --color-warning | #F59E0B | 警告、待处理 |
| --color-warning-light | #FFFBEB | 警告浅底 |
| --color-danger | #DC2626 | 错误、失败、危险操作 |
| --color-danger-light | #FEF2F2 | 错误浅底 |
| --color-info | #2563EB | 信息提示（复用主色）|

### 中性色（Neutral）

| Token | 值 | 用途 |
|-------|------|------|
| --color-bg-base | #F8FAFC | 页面底色 |
| --color-bg-surface | #FFFFFF | 卡片/面板底色 |
| --color-bg-elevated | #F1F5F9 | 表头、hover 行底色 |
| --color-border-subtle | #F1F5F9 | 分割线（极淡）|
| --color-border-default | #E2E8F0 | 卡片/输入框边框 |
| --color-border-strong | #CBD5E1 | 强调边框 |

### 文字色

| Token | 值 | 用途 |
|-------|------|------|
| --color-text-primary | #0F172A | 标题、关键信息 |
| --color-text-secondary | #475569 | 正文、描述 |
| --color-text-tertiary | #94A3B8 | 辅助说明、placeholder |
| --color-text-disabled | #CBD5E1 | 禁用态文字 |
| --color-text-inverse | #FFFFFF | 深色背景上的文字 |

---

## 2. 字体

| Token | 值 |
|-------|------|
| --font-family | -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", Arial, sans-serif |
| --font-size-xs | 12px |
| --font-size-sm | 13px |
| --font-size-base | 14px |
| --font-size-lg | 16px |
| --font-size-xl | 20px |
| --font-size-2xl | 24px |
| --font-weight-normal | 400 |
| --font-weight-medium | 500 |
| --font-weight-semibold | 600 |
| --line-height-tight | 1.4 |
| --line-height-normal | 1.6 |

---

## 3. 间距

基于 4px 网格：

| Token | 值 | 常用场景 |
|-------|------|----------|
| --space-1 | 4px | 图标与文字间距 |
| --space-2 | 8px | 紧凑元素间距 |
| --space-3 | 12px | 表单项内间距 |
| --space-4 | 16px | 卡片内边距、列表项间距 |
| --space-5 | 20px | 区块间距 |
| --space-6 | 24px | 卡片内边距（宽松）|
| --space-8 | 32px | 页面区块间距 |
| --space-10 | 40px | 页面上下留白 |

---

## 4. 圆角

| Token | 值 | 用途 |
|-------|------|------|
| --radius-sm | 4px | 小按钮、标签 |
| --radius-md | 6px | 输入框、下拉 |
| --radius-lg | 8px | 卡片、弹窗 |
| --radius-xl | 12px | 大面板、模态 |
| --radius-full | 9999px | 圆形头像、胶囊按钮 |

---

## 5. 阴影

| Token | 值 | 用途 |
|-------|------|------|
| --shadow-sm | 0 1px 2px rgba(15,23,42,0.04) | 输入框、小卡片 |
| --shadow-md | 0 2px 8px rgba(15,23,42,0.06) | 卡片默认 |
| --shadow-lg | 0 4px 16px rgba(15,23,42,0.08) | 悬浮卡片、下拉面板 |
| --shadow-xl | 0 8px 32px rgba(15,23,42,0.12) | 弹窗、Modal |

---

## 6. 组件规范快查

### 按钮

| 场景 | 尺寸 | 规范 |
|------|------|------|
| 页面主操作 | 默认(32px高) | type="primary" |
| 表格行内操作 | small(28px高) | type="text" 或 type="outline" |
| 紧凑工具栏 | mini(24px高) | 仅限 IDE 类页面（SqlDev、WorkflowEditor）|

### 表格

- 统一使用 `<a-table>` + `<a-table-column>` slot 写法
- 行高：紧凑型 `size="small"`（数据密集页面）
- 斑马纹：关闭（用 hover 高亮替代）

### 卡片

- 统一用 `.glass-card` 类名
- 内边距：24px（--space-6）
- 圆角：8px（--radius-lg）
- 阴影：--shadow-md
- 无边框（border: none）

### 页面标题

- 标签：`<h3 class="page-title">`
- 字号：20px（--font-size-xl）
- 字重：600（--font-weight-semibold）
- 下方描述：--color-text-secondary，--font-size-sm

### 状态标签

| 状态 | 颜色 | 文字 |
|------|------|------|
| 成功/已完成 | success | 成功 / 已完成 |
| 运行中 | primary | 运行中 |
| 等待中 | warning | 等待中 / 待处理 |
| 失败 | danger | 失败 |
| 已禁用 | neutral(#94A3B8) | 已禁用 / 已过期 |

---

## 7. 设计原则

1. **克制** — 页面最多出现 2 种强调色（主色 + 一个状态色）
2. **呼吸感** — 区块之间保留 24-32px 间距，不要挤
3. **层次** — 用文字色阶和阴影制造层次，少用边框
4. **一致** — 同类元素同种处理，不造新轮子
