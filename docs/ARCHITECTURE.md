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

---

### [高] DataX 运行无队列/并发保护

**问题**：`POST /sync-tasks/{id}/run` 直接 subprocess 执行，多用户同时运行同一任务会并发冲突，目标表数据可能损坏。

**风险**：生产数据错乱。

**建议方案**：运行前检查 `last_run_status == 'RUNNING'`（需新增此状态），或用 Redis 分布式锁，或改为提交到 DolphinScheduler 队列执行。

---

### [高] 后端组件/任务运行没有超时保护

**问题**：`run_component`（SQL/Python/Shell）和 `run_sync_task` 的 subprocess 超时设为 600s，但 SQL 查询没有数据库层面的超时，长 SQL 会挂住整个 worker 进程。

**风险**：FastAPI worker 被占满，整个后端无响应。

**建议方案**：SQL 执行加 `SET SESSION max_execution_time=30000`（MySQL），Python/Shell 保持 subprocess timeout。

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

### [低] 后端 Dockerfile 使用 --reload（开发模式）

**问题**：`CMD ["uvicorn", "main:app", "--reload", ...]` 在生产环境不应开启 reload，有安全风险且性能差。

**建议方案**：上线前去掉 `--reload`，加 `--workers 2`。

---

### [低] .env 含真实密码提交到仓库

**问题**：MVP 阶段为方便部署，`.env` 未加入 `.gitignore`，密码明文在仓库中。

**建议方案**：正式上线前将 `.env` 加入 `.gitignore`，密码改为 docker-compose secrets 或环境变量注入。

---

### [低] CORS 配置为 * + Cookie 无 Secure 标志

**问题**：`CORS allow_origins=["*"]`，`COOKIE_SECURE=False`，仅适用于 HTTP 内网环境。

**建议方案**：上线前改为明确域名，启用 HTTPS 后设 `COOKIE_SECURE=True`。

---

## 已解决 ✅

- ✅ **workflow dag_json 节点名称快照问题** — 改名时已自动同步（2026-05，`_sync_component_name_in_workflows`）
- ✅ **组件无编辑锁** — 已加 locked_by/locked_at + 30分钟TTL（2026-05）
- ✅ **DS OOM** — 内存限制从 2g 提升到 4g（2026-05）
- ✅ **MySQL 中文乱码** — docker-compose 加 utf8mb4 强制配置（2026-05）
