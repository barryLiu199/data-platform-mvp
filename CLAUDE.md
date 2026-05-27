# 数据中台 MVP — 项目架构地图

> 本文件供 Claude Code 每次对话自动加载，实现"改一处知全局影响"的最小化改动策略。

## 项目概览

- **定位**：金融行业离线数据中台统一门户
- **技术栈**：Vue3 + Arco Design（前端）| FastAPI + SQLAlchemy（后端）| DolphinScheduler 3.2.2（调度）| MySQL 8.0 + Redis 7
- **部署**：Docker Compose 单机，Nginx 反向代理，对外仅 :80
- **服务器**：47.92.236.44（阿里云 Ubuntu 22.04），项目路径 `/root/data-platform-mvp`

## 目录结构

```
data-platform-mvp/
├── docker-compose.yml          # 6 个服务：nginx, portal-frontend, portal-backend, ds, mysql, redis
├── .env                        # 环境变量（数据库密码、密钥等）
├── nginx/nginx.conf            # 反向代理：/ → 前端SPA, /api/ → portal-backend:8000
├── datax/                      # DataX 引擎（挂载到 DS 容器）
├── drivers/                    # JDBC 驱动（mysql-connector-j-8.0.33.jar）
├── portal/
│   ├── backend/                # FastAPI 后端
│   │   ├── main.py             # 入口：建表、迁移、种子数据、注册路由
│   │   ├── app/
│   │   │   ├── api/            # 路由层（14 个模块）
│   │   │   ├── core/           # 基础设施（11 个模块）
│   │   │   └── models/         # 数据模型（17 个表）
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── frontend/               # Vue3 前端
│       ├── src/
│       │   ├── api/index.ts    # 全部 API 函数（~90 个）
│       │   ├── router/index.ts # 路由定义 + 权限守卫
│       │   ├── stores/user.ts  # 唯一 Pinia store
│       │   ├── styles/
│       │   │   ├── tokens.css  # CSS 变量 — 唯一色值来源
│       │   │   └── global.css  # Arco 覆盖 + .glass-card（引用 tokens.css）
│       │   ├── constants/
│       │   │   └── status.ts   # 状态颜色/文案统一映射（执行/生命周期/同步）
│       │   ├── views/          # 页面组件（22 个）
│       │   ├── components/     # 复用组件（17 个，含 5 个共享 UI 组件）
│       │   ├── composables/    # useFileTree
│       │   ├── directives/     # v-permission
│       │   └── layouts/        # BasicLayout.vue
│       └── Dockerfile
```

## 后端模块依赖（改动影响分析）

### 核心层 (app/core/) — 被多个 API 依赖，改动影响面大

| 模块 | 职责 | 被谁依赖 |
|------|------|---------|
| `config.py` | 全局配置(Settings) | database, security, ds_client |
| `database.py` | SQLAlchemy 引擎/会话 | 所有 API 模块（通过 get_db） |
| `security.py` | 密码哈希/JWT/get_current_user | 所有需认证的 API + main.py |
| `permissions.py` | RBAC 权限检查 | datasources, sync_tasks, component, workflow, metadata, system, alert_rules, word_roots, admin/* |
| `ds_client.py` | DolphinScheduler HTTP 客户端 | dashboard, ds_proxy, workflow, system |
| `dsl_translator.py` | 工作流 DAG → DS 格式转换 | workflow |
| `datax_builder.py` | DataX JSON 配置生成 | sync_tasks |
| `db_adapter.py` | 多数据源连接/查询 | metadata, datasources |
| `notifier.py` | 告警通知(邮件/钉钉/飞书/企微) | alert_rules |
| `migrations.py` | DDL 迁移脚本 | main.py（启动时执行） |
| `oauth.py` | SSO 三方登录 | auth |

### API 路由层 (app/api/) — 每个模块相对独立

| 模块 | 路由前缀 | 依赖的 core | 依赖的 models |
|------|---------|------------|--------------|
| `auth.py` | `/auth` | security, config | SysUser |
| `datasources.py` | `/datasources` | security, permissions | DataSource |
| `sync_tasks.py` | `/sync-tasks` | security, permissions | SyncTask, DataSource |
| `dashboard.py` | `/dashboard` | security, ds_client | DataSource, SyncTask, Workflow, WordRoot |
| `ds_proxy.py` | `/ds` | security, permissions, ds_client | Workflow |
| `component.py` | `/components` | security, permissions | Component, ComponentFolder |
| `workflow.py` | `/workflows` | security, permissions, ds_client, dsl_translator | Workflow, WorkflowVersion, Component, DataSource |
| `metadata.py` | `/metadata` | security, permissions | DataSource |
| `system.py` | `/system` | permissions, ds_client | — |
| `notifications.py` | `/notifications` | security | Notification |
| `alert_rules.py` | `/alert-rules` | security, permissions, notifier | AlertRule, Workflow |
| `word_roots.py` | `/word-roots` | security, permissions | WordRoot |
| `project.py` | `/projects` | security, permissions | Project, SyncTask |
| `admin/*` | `/admin/*` | permissions | SysUser, SysRole, SysOAuthConfig, SysConfig, SysResourceAccess, SysNotifyChannel |

### 数据模型 (app/models/) — 18 张表

| 模型 | 表名 | 被哪些 API 使用 |
|------|------|---------------|
| `SysUser` | sys_user | auth, admin/users, dashboard |
| `DataSource` | data_source | datasources, sync_tasks, metadata, workflow, dashboard |
| `SyncTask` | sync_task | sync_tasks, project, dashboard |
| `Component` | component | component, workflow |
| `ComponentFolder` | component_folder | component |
| `Workflow` | workflow | workflow, ds_proxy, alert_rules, dashboard, project |
| `WorkflowVersion` | workflow_version | workflow（版本历史/回滚） |
| `WordRoot` | word_root | word_roots, dashboard |
| `Notification` | notification | notifications |
| `AlertRule` | alert_rule | alert_rules |
| `Project` | project | project（含 workflow_count 统计） |
| `SysRole/Permission/RolePerm/UserRole` | sys_role/* | auth, admin/roles, admin/users, main.py(种子) |
| `SysResourceAccess` | sys_resource_access | admin/resource_access, permissions |
| `SysOAuthConfig` | sys_oauth_config | admin/sso, auth |
| `SysConfig` | sys_config | admin/config |
| `SysNotifyChannel` | sys_notify_channel | admin/notify_channels |

## 前端路由 → 页面 → API 映射

| 路由 | 页面文件 | 菜单位置 | 调用的后端 API |
|------|---------|---------|--------------|
| `/dashboard` | Dashboard.vue | 工作台 | GET /dashboard/stats, GET /ds/instances |
| `/datasources` | DataSource.vue | 系统管理 > 数据源管理 | /datasources CRUD, POST /datasources/{id}/test |
| `/sql-dev` | SqlDev.vue | 数据开发 > 组件开发 | /components CRUD, /components/folders, POST /components/run-sql |
| `/workflows` | Workflow.vue | 数据开发 > 工作流开发 | /workflows CRUD, /workflows/{id}/publish\|offline\|run |
| `/workflows/:id/edit` | WorkflowEditor.vue | (编辑页) | GET/PUT /workflows/{id}, POST /workflows/{id}/test\|publish\|run |
| `/scheduler/history` | SchedulerHistory.vue | 运维中心 > 运行实例 | GET /ds/instances, GET /ds/instances/{id}/tasks |
| `/ops/instances/:id` | InstanceDetail.vue | (详情页) | GET /ds/instances/{id}/tasks, GET /ds/tasks/{id}/log |
| `/alerts` | AlertCenter.vue | 运维中心 > 监控规则 | /alert-rules CRUD, POST /alert-rules/test-notify |
| `/data-assets` | DataAssets.vue | 数据资产 > 数据目录 | GET /metadata/tables\|columns\|preview, GET /datasources |
| `/field-assets` | FieldAssets.vue | 数据资产 > 词根管理 | /word-roots CRUD, POST /word-roots/import |
| `/lineage` | DataLineage.vue | 数据资产 > 数据血缘 | GET /metadata/lineage |
| `/monitor` | Monitor.vue | 系统管理 > 系统监控 | GET /system/services, GET /system/info, GET /ds/monitor |
| `/admin/users` | admin/Users.vue | 系统管理 > 用户管理 | /admin/users CRUD, GET /admin/roles |
| `/admin/roles` | admin/Roles.vue | 系统管理 > 角色管理 | /admin/roles CRUD, GET /admin/permissions |
| `/admin/sso` | admin/Sso.vue | 系统管理 > SSO 配置 | GET/PUT /admin/sso |
| `/admin/notify` | admin/Notify.vue | 系统管理 > 通知配置 | (占位页，未接入 API) |
| `/login` | Login.vue | (独立页) | POST /auth/login, GET /admin/sso/public |

### 前端组件依赖

#### 共享 UI 组件（Design Token 体系）

| 组件 | 用在哪些页面 | 说明 |
|------|------------|------|
| `PageHeader.vue` | DataSource, Workflow, Component, AlertCenter, Monitor, DataAssets, FieldAssets, SchedulerTasks, admin/Users, admin/Roles, admin/Sso | 统一页面标题+描述+右侧操作区 |
| `StatusTag.vue` | Workflow, Component | 统一状态标签，引用 status.ts |
| `FilterTabs.vue` | Workflow, Component, FieldAssets | 统一筛选标签栏 v-model |
| `EmptyState.vue` | Workflow, Component, AlertCenter, SchedulerTasks | 统一空状态展示 |
| `FileTreePanel.vue` | SqlDev, DagNodePanel | 共享文件树面板（组头彩色竖条+LangIcon叶子节点），支持编辑/拖拽/只读模式 |

#### 业务组件

| 组件 | 用在哪些页面 | 调用的 API |
|------|------------|-----------|
| `CodeEditor.vue` | SqlDev, WorkflowEditor | /metadata/tables, /metadata/columns（自动补全），暴露 formatDocument（sql-formatter 格式化） |
| `SqlParamModal.vue` | SqlDev | —（纯前端组件，检测 SQL 中 ${xxx} 参数，弹窗填值，类型感知输入+日期快捷+自动加引号+SQL预览） |
| `SyncTaskCanvas.vue` | SqlDev | /sync-tasks CRUD, /datasources, /metadata/* |
| `SyncTaskWizard.vue` | SqlDev | /sync-tasks, /datasources, /metadata/*, /components |
| `FieldMappingCanvas.vue` | SyncTaskCanvas, SyncTaskWizard | — |
| `ScheduleModal.vue` | Workflow | POST /workflows/cron-preview |
| `dag/DagCanvas.vue` | WorkflowEditor | — |
| `dag/DagNodePanel.vue` | WorkflowEditor | GET /components/folders, GET /components, GET /sync-tasks（使用 FileTreePanel） |
| `dag/DagCustomNode.vue` | DagCanvas | — |
| `dag/DagContextMenu.vue` | DagCanvas | — |
| `dag/DagToolbar.vue` | DagCanvas | — |
| `LangIcon.vue` | DagNodePanel, DagCustomNode, SqlDev | — |
| `ContextMenu.vue` | SqlDev | — |

## 改动影响速查（常见场景）

改什么 → 需要同时检查什么：

| 改动 | 影响范围 |
|------|---------|
| 改 `DataSource` 模型字段 | datasources.py, sync_tasks.py, metadata.py, workflow.py, dashboard.py, db_adapter.py, datax_builder.py, 前端 DataSource.vue |
| 改 `Component` 模型字段 | component.py, workflow.py(引用组件), dsl_translator.py, 前端 SqlDev.vue, WorkflowEditor.vue |
| 改 `Workflow` 模型字段 | workflow.py, ds_proxy.py, alert_rules.py, dashboard.py, dsl_translator.py, project.py(workflow_count), 前端 Workflow.vue, WorkflowEditor.vue |
| 改 `security.py` (认证) | 所有需认证的 API 都受影响，前端 401 拦截逻辑(api/index.ts) |
| 改 `permissions.py` | 所有带 require_permission 的 API，前端 v-permission 指令 |
| 改 `ds_client.py` | dashboard.py, ds_proxy.py, workflow.py, system.py |
| 改 `api/index.ts` (前端API) | 所有引用该函数的 views/components |
| 改 `router/index.ts` | BasicLayout.vue 菜单需同步 |
| 改 `BasicLayout.vue` 菜单 | router/index.ts 路由需同步 |
| 改 `docker-compose.yml` | nginx.conf(端口/服务名), .env(环境变量) |
| 改 `config.py` Settings | docker-compose.yml 环境变量需同步 |
| 改 `tokens.css` 色值 | global.css Arco 覆盖、tailwind.config.js 需同步，影响全站所有页面 |
| 改 `status.ts` 状态映射 | SchedulerHistory, InstanceDetail, Workflow, Component, SchedulerTasks, SyncTaskCanvas |
| 改 `PageHeader.vue` | 13 个使用该组件的页面全部受影响 |

## 部署流程

```bash
# 服务器：root@47.92.236.44，密码 lt720912.
# 项目路径：/root/data-platform-mvp

# 1. 拉代码
cd /root/data-platform-mvp && git pull origin main

# 2. 重建前端（约2-3分钟）
docker compose up -d --build portal-frontend
# nginx 自动挂载 frontend_dist 卷，无需重启

# 3. 重建后端（约1-2分钟）
docker compose up -d --build portal-backend

# 4. 全部重建
docker compose up -d --build

# 注意：DS 内存限制 4g，启动需要 2-3 分钟
```

## 注意事项

- **前端设计规范**：主色 `#2563EB`（方案A蓝白），所有色值必须通过 `var(--color-xxx)` 或 Tailwind token 引用，禁止硬编码 hex。新页面必须使用 PageHeader 组件，状态展示用 StatusTag 或 `status.ts`
- 前端构建跳过了 vue-tsc 类型检查（package.json build script 只跑 vite build）
- DS standalone 模式 JVM 峰值内存 ~2.7GB，docker-compose 限制 4g
- `.env` 包含真实密码已提交仓库（MVP 阶段）
- 后端 Dockerfile 启动用了 `--reload`（开发模式），生产应去掉
- CORS 配置为 `["*"]`，COOKIE_SECURE=False（HTTP 环境）
- REDIS_URL 和 DS_ADMIN_PASSWORD 未通过 docker-compose 注入，使用 config.py 默认值

## 知识库索引

| 文档 | 内容 | 何时查阅 |
|------|------|---------|
| `docs/PITFALLS.md` | 踩坑记录：现象 → 根因 → 正确做法 | 遇到 bug / 修复前先看有没有先例 |
| `docs/ARCHITECTURE.md` | 架构债务清单：已知设计问题 + 风险 + 建议方案 | 修改涉及并发/锁/超时/部署时先查 |

> **规则**：每次 git push 前，如果修复了 bug 必须追加到 `docs/PITFALLS.md`；发现架构问题追加到 `docs/ARCHITECTURE.md`。

---

## Agent skills

### Issue tracker

GitHub Issues on `barryLiu199/data-platform-mvp`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary (needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — `CONTEXT.md` + `docs/adr/` at repo root. See `docs/agents/domain.md`.
