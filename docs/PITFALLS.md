# PITFALLS.md — 踩坑记录

> 每次修复 bug 或反复改动后追加。格式：**现象 → 根因 → 正确做法**。
> 目的：同一个坑不踩第二次。

---

## [2026-05] Tab 溢出检测改了三次

**现象**：SqlDev 组件开发页面，打开多个 tab 后溢出按钮不显示，或显示数量不对。

**踩坑过程**：
1. 第一版：`Math.floor(containerWidth / 140)` 估算可见数 → 因 tab 宽度不固定，估算不准
2. 第二版：改为观测 `.tab-bar` 父容器 + 初始 maxVisible=100 → 还是不准确
3. 第三版（正确）：渲染全部 tab，CSS `overflow:hidden` 自然裁剪，用 `ResizeObserver` 测量每个子元素 `offsetLeft + offsetWidth > containerWidth` 来判断溢出起始索引

**根因**：不能用宽度估算，必须用 DOM 实际位置测量。先渲染再测量，不能测量未渲染的元素。

**正确做法**：
```typescript
// SqlDev.vue — recalcVisibleTabs()
for (let i = 0; i < children.length; i++) {
  if (el.offsetLeft + el.offsetWidth > containerWidth) {
    newStart = i; break
  }
}
```

**涉及文件**：`portal/frontend/src/views/SqlDev.vue`

---

## [2026-05] MySQL Adapter DictCursor 导致元数据返回 0

**现象**：数据目录页面读取表/字段元数据，返回 0 条结果，无报错。

**根因**：`mysql.py` adapter 中添加了 `cursorclass=pymysql.cursors.DictCursor`，但后续代码全部用 `r[0]`、`r[1]` 位置索引访问，DictCursor 返回 dict 导致 `r[0]` 取不到值。

**正确做法**：不加 DictCursor，保持默认 tuple cursor，位置索引正常工作。

**涉及文件**：`portal/backend/app/core/db_adapters/mysql.py`

---

## [2026-05] right-bar 遮挡工具栏按钮

**现象**：SqlDev 右侧 Activity Bar（36px，position:absolute）盖住了 tab-bar 最右侧的"+"按钮和工具栏最右侧的参数按钮。

**根因**：right-bar 是 `position: absolute; right: 0; z-index: 11`，会盖在正常流元素上。

**正确做法**：不改 right-bar 定位，在被遮挡的容器上**单独加一行** `padding-right`，保留原 padding shorthand 不动：
```css
.tab-bar { padding-right: 40px; }   /* 36px bar + 4px 间距 */
.ide-toolbar { padding-right: 48px; } /* 36px bar + 12px 间距 */
.canvas-header { padding-right: 56px; } /* DataX面板同理 */
```

**规则**：每次新增被 right-bar 覆盖的横向容器，都加这一行，不要改 position/z-index。

**涉及文件**：`portal/frontend/src/views/SqlDev.vue`, `portal/frontend/src/components/SyncTaskCanvas.vue`

---

## [2026-05] MySQL 中文 COMMENT 乱码（双重 UTF-8 编码）

**现象**：ADS 数据源的表/字段 COMMENT 显示乱码，ODS 正常。

**根因**：数据存储时发生了双重 UTF-8 编码——UTF-8 字节被当作 latin1 存入再读出，导致乱码。MySQL 连接字符集配置不一致（通过 SSH 执行 DDL 时未设置 utf8mb4）。

**正确做法**：
1. `docker-compose.yml` MySQL 服务加 `--character-set-client-handshake=FALSE` 和 `--init-connect="SET NAMES utf8mb4"`
2. 已损坏的数据：用 `SET character_set_results = latin1` 读出原始字节，再用 `ALTER TABLE ... COMMENT=` 重写正确值

**涉及文件**：`docker-compose.yml`, 数据修复脚本（一次性，已执行）

---

## [2026-05] PyMySQL charset='latin1' 无法用于读取双编码数据

**现象**：尝试用 `charset='latin1'` 连接读取乱码数据，出现两种错误：
- `use_unicode=True`：`LookupError: unknown encoding cp1252`（0x81 未定义）
- `use_unicode=False`：`TypeError: query params must be str not bytes`

**正确做法**：保持 `charset='utf8mb4'` 连接，执行 `SET character_set_results = latin1` 语句让 MySQL 返回原始字节，绕过服务端转码。

---

## [2026-05] workflow dag_json 节点名称是快照

**现象**：重命名组件后，工作流画布上的节点名称没有变化。

**根因**：`dag_json` 的 nodes 在拖入工作流时 snapshot 了组件名，不是实时查询。

**已修复**：`update_component` 改名时扫描所有 workflow 的 `dag_json.nodes` 和 `steps_json`，把 `component_id` 匹配的节点 name 同步更新。

**涉及文件**：`portal/backend/app/api/component.py` — `_sync_component_name_in_workflows()`

---

## [2026-05] DataX 任务手动触发没有锁保护

**现象**：多用户同时点"运行"可能并发执行同一个 DataX 任务。

**状态**：已知架构债务，见 `ARCHITECTURE.md`。
