# ARCHITECTURE.md — 架构债务清单

> 已知的设计问题、技术债务、需要重构的地方。
> 格式：**问题描述 → 风险 → 建议方案**。
> 发现新问题随时追加，解决后标记 ✅。

---

## 待解决

### [高] Backfill 执行进程依赖 FastAPI BackgroundTask，重启会丢实例

**问题**：`POST /backfill` 创建任务后用 `BackgroundTasks` + `asyncio.run(_run_backfill)` 在 portal-backend 进程内跑。容器重启 / `--reload` 触发 / OOM 时，正在执行的实例 status 永远卡在 `running`，再也不会推进。

**风险**：补数据假死。用户重试又会重复触发已经成功的日期（DataX 没幂等保护）。

**建议方案**：
- 临时：portal-backend 启动时加 reaper —— 把所有 status='running' 但 started_at > 1h 前的实例改成 'failed'，error_msg='进程重启遗留'。
- 长期：Backfill 应该把每个 instance 提交到 DolphinScheduler 跑（复用 workflow 的 ds_process_code + startParams），由 DS 保证持久化与重试，portal-backend 只做编排和状态轮询。

**状态**：✅ 已解决(2026-05-28)— 编排完全迁移到 DS complement API。一次 `complement_data()` 调用让 DS 自动按日展开实例，portal 只做状态轮询。新增 reaper 启动时恢复同步、stop 真正终止 DS 实例。

---

### [高] DataX 运行无队列/并发保护

**问题**：`POST /sync-tasks/{id}/run` 直接 subprocess 执行，多用户同时运行同一任务会并发冲突，目标表数据可能损坏。

**风险**：生产数据错乱。

**建议方案**：运行前检查 `last_run_status == 'RUNNING'`（需新增此状态），或用 Redis 分布式锁，或改为提交到 DolphinScheduler 队列执行。

**状态**：✅ 已解决(2026-05-28)— `POST /sync-tasks/{id}/run` 已改为统一走 DS 调度：自动 publish-as-workflow（幂等）+ start_process_instance。subprocess 路径已废弃，并发控制由 DS 队列保证。

---

### [高] 后端组件/任务运行没有超时保护

**问题**：`run_component`（SQL/Python/Shell）和 `run_sync_task` 的 subprocess 超时设为 600s，但 SQL 查询没有数据库层面的超时，长 SQL 会挂住整个 worker 进程。

**风险**：FastAPI worker 被占满，整个后端无响应。

**建议方案**：SQL 执行加 `SET SESSION max_execution_time=30000`（MySQL），Python/Shell 保持 subprocess timeout。

**状态**：✅ 已解决(2026-05-22)— mysql/postgresql/sqlserver/clickhouse 四个 adapter 的 connect() 均加了 session 级超时（`SQL_QUERY_TIMEOUT_SEC` env 可配，默认 30s）。

---

### [中] 编辑锁没有心跳续期

**问题**：锁 TTL 30 分钟，用户打开组件后一直编辑不保存，30 分钟后锁过期，另一个用户可以抢锁并覆盖。

**风险**：多人编辑冲突（概率低但存在）。

**建议方案**：前端每 10 分钟调一次 `POST /lock`（自动续期），或用 WebSocket 保持心跳。

---

### [中] workflow dag_json 无版本校验

**问题**：两个用户同时编辑同一个工作流，后保存的会覆盖先保存的，无乐观锁保护。

**风险**：工作流配置丢失。

**建议方案**：`PUT /workflows/{id}` 加 `If-Match: version` 校验，前端传当前 version，不一致返回 409。

---

### [中] DataX subprocess 在 portal-backend 容器内执行

**问题**：DataX 需要 Python 环境和 `/opt/datax`，目前在 portal-backend 容器里执行，耦合度高，资源隔离差。

**风险**：DataX 任务消耗大量 CPU/内存会影响 API 响应。

**建议方案**：长期应将 DataX 执行迁移到 DolphinScheduler worker 节点（已有 `publish-as-workflow` 路径），直接运行端点作为临时方案。

---

### [低] 后端 Dockerfile 使用 --reload(开发模式)

**问题**:`CMD ["uvicorn", "main:app", "--reload", ...]` 在生产环境不应开启 reload,有安全风险且性能差。

**建议方案**:上线前去掉 `--reload`,加 `--workers 2`。

**状态**:✅ 已解决(2026-05-22)— 切换为 `gunicorn -k uvicorn.workers.UvicornWorker -w ${GUNICORN_WORKERS:-4}`,worker/timeout 走环境变量。

---

### [中] 前端 build 跳过 vue-tsc 类型检查

**问题**:`package.json` 的 `build` 只跑 `vite build`,未跑 `vue-tsc --noEmit`,类型错误进不了 CI 门禁。当前累积 10 个历史类型错误(主要来自 Arco Design 类型签名严格化)。

**风险**:类型层的契约破坏被静默放过,组件 props/事件签名漂移。

**建议方案**:
- 新增 `type-check` 与 `build:strict` 脚本,CI/上线前必跑 `build:strict`。
- 旧错误分批清理:先把 admin/Roles、admin/Sso、admin/Users、SqlDev、Workflow、WorkflowEditor 这 6 个文件的类型错误清掉,即可启用 `build:strict` 作为默认 `build`。

**状态**：✅ 已解决(2026-05-22)— 10 处 TS 错误全部清理，`build` 脚本已切为 `vue-tsc --noEmit && vite build`，旧宽松构建保留为 `build:loose`。

---

### [低] .env 含真实密码提交到仓库

**问题**:MVP 阶段为方便部署,`.env` 未加入 `.gitignore`,密码明文在仓库中。

**建议方案**:正式上线前将 `.env` 加入 `.gitignore`,密码改为 docker-compose secrets 或环境变量注入。`git filter-repo` 清洗历史。

**状态**:未解决(下批次处理,需 force-push)。

---

### [低] CORS 配置为 * + Cookie 无 Secure 标志

**问题**:`CORS allow_origins=["*"]`,`COOKIE_SECURE=False`,仅适用于 HTTP 内网环境。

**建议方案**:上线前改为明确域名,启用 HTTPS 后设 `COOKIE_SECURE=True`。

**状态**:✅ 部分解决(2026-05-22)— `CORS_ORIGINS` 改为环境变量驱动的白名单(默认 `http://47.92.236.44,http://localhost:5173,http://127.0.0.1:5173`),`COOKIE_SECURE` 也走 env。等 HTTPS 上线后把 `COOKIE_SECURE=True` 切上即可。

---

## 已解决 ✅

- ✅ **后端生产模式化(P0)** — Dockerfile 切 gunicorn + UvicornWorker(2026-05-22)
- ✅ **CORS 白名单化(P0)** — `CORS_ORIGINS` 走 env,默认非 `*`,新增 `field_validator` 解析逗号分隔(2026-05-22)
- ✅ **Cookie 安全开关(P0)** — `COOKIE_SECURE` 走 env(2026-05-22)
- ✅ **REDIS_URL / DS_ADMIN_PASSWORD compose 注入(P0)** — 不再依赖 config.py 默认值(2026-05-22)
- ✅ **前端 type-check 脚本(P0)** — 新增 `type-check` / `build:strict`,留作 CI 门禁(2026-05-22)
- ✅ **前端 Playwright 冒烟(P0)** — `e2e/login.spec.ts` 5 条主路径(2026-05-22)
- ✅ **SQL 查询超时保护(P0)** — mysql/postgresql/sqlserver/clickhouse adapter 加 session 级超时，默认 30s(2026-05-22)
- ✅ **前端 TS 错误清理(P0)** — 10 处错误修复，`build` 默认 strict(2026-05-22)
- ✅ **workflow dag_json 节点名称快照问题** — 改名时已自动同步(2026-05,`_sync_component_name_in_workflows`)
- ✅ **组件无编辑锁** — 已加 locked_by/locked_at + 30分钟TTL(2026-05)
- ✅ **DS OOM** — 内存限制从 2g 提升到 4g(2026-05)
- ✅ **MySQL 中文乱码** — docker-compose 加 utf8mb4 强制配置(2026-05)
