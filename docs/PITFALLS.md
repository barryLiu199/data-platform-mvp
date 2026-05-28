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

## [2026-05] passlib 1.7.4 + bcrypt 4.x 兼容性导致登录 401

**现象**：部署到新服务器后，输入正确密码无法登录，始终停在登录页。后端日志：
```
AttributeError: module 'bcrypt' has no attribute '__about__'
POST /api/auth/login 401
```

**根因**：passlib 1.7.4 已停止维护（最后发版 2020 年），启动时尝试读取 `bcrypt.__about__.__version__` 获取版本号，而 bcrypt 4.x 移除了 `__about__` 属性，导致整个 bcrypt backend 初始化失败，`pwd_context.verify()` 全部抛异常，登录永远返回 401。

**次生问题**：passlib 生成的 hash 使用了错误的 padding bits（警告：`encountered a bcrypt hash with incorrectly set padding bits`），导致旧 hash 无法被原生 bcrypt 直接验证，需要重置密码。

**修复**：
1. `requirements.txt` 删除 `passlib[bcrypt]==1.7.4`，保留 `bcrypt==4.1.3`
2. `security.py` 的 `hash_password`/`verify_password` 直接调 `bcrypt.hashpw`/`bcrypt.checkpw`，接口签名不变，其他文件零改动
3. `test_security.py` 去掉 mock，改为真实 bcrypt 测试
4. 数据库里旧的 passlib hash 需要重置：
```bash
# 在服务器上重置 admin 密码
NEW_HASH=$(docker exec dmp-portal-api python3 -c "import bcrypt; print(bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode())")
docker exec -i dmp-mysql mysql -uroot -pDpMvp2026Secure portal_db \
  -e "UPDATE sys_user SET password='$NEW_HASH' WHERE username='admin';"
```

**经验**：依赖已停更 5 年的库（passlib）是架构债务。bcrypt 本来就是 passlib 的唯一后端，中间层没有价值。新服务器部署后第一件事先查 `/api/health`，再用 curl 测登录接口，不要直接在浏览器试。

**涉及文件**：`portal/backend/app/core/security.py`、`requirements.txt`、`tests/test_security.py`

---



**现象**：多用户同时点"运行"可能并发执行同一个 DataX 任务。

**状态**：已知架构债务，见 `ARCHITECTURE.md`。

---

## [2026-05] 补数 502：DS 3.2.x scheduleTime 必须是 JSON 而非逗号分隔

**现象**：工作流页 → 更多 → 补数 → 选日期范围 → 提交，前端 toast "补数失败"，浏览器 Network 502 Bad Gateway。`backfill_task` 表 0 行（说明根本没走新引擎）。

**根因**：
1. UI 有**两套补数**并存——工作流页/调度历史页的旧"补数"按钮用的是 `POST /api/ds/workflows/{code}/complement`，前端文件 `ComplementModal.vue`；运维中心 → 补数据 是新的 `POST /api/backfill`（新表 + asyncio 引擎）。用户的心智模型是从工作流入口发起，永远进的是旧路径。
2. 旧路径把 `scheduleTime` 拼成 `"2026-05-14 00:00:00,2026-05-21 00:00:00"`（DS 2.x 老格式）。DS 3.2.2 `ExecutorServiceImpl.checkScheduleTimeNumExceed:308` 调 `JSONUtils.toMap(cronTime)` 解析为 JSON map，失败抛 `JsonParseException`，外层 `ApiExceptionHandler` 转 `NullPointerException`，portal 收到 null 返 502。
3. DS 3.2.x 期望 `scheduleTime = '{"complementStartDate":"...","complementEndDate":"..."}'`（或 `complementScheduleDateList`）。

**DS 日志关键证据**：
```
[ERROR] o.a.d.c.u.JSONUtils: json to map exception!
JsonParseException: Unexpected character ('-' (code 45))
 at [Source: (String)"2026-05-14 00:00:00,2026-05-21 00:00:00"; line: 1, column: 6]
  at ExecutorServiceImpl.checkScheduleTimeNumExceed(308)
  at ExecutorServiceImpl.execProcessInstance(259)
```

**正确做法**：合一到 portal 自研的 backfill 引擎（START_PROCESS + startParams 传 `${bizdate}`），不走 DS 原生 COMPLEMENT_DATA：
1. **删除** `ComplementModal.vue` + `complementDSWorkflow` API + `ds_proxy.py /complement` 端点（保留为 HTTP 410 提示）。
2. **新建** `BackfillCreateModal.vue`，工作流页 + WorkflowEditor 的"补数"按钮统一弹此 Modal，调 `POST /api/backfill`。
3. **Backfill.vue** 改为纯监控页（无创建按钮），与 DataWorks 一致：发起跟着工作流走，监控集中在运维中心。
4. **SchedulerHistory.vue** 移除"补数"按钮（运行实例列表不发起补数，与 DataWorks/DolphinScheduler/Airflow 一致）。
5. `_run_one()` 用 START_PROCESS 模式 + `start_params=JSON({bizdate:...})`，**不**走 COMPLEMENT_DATA，因此不传 scheduleTime，绕过 DS 此 bug。`ExecutorServiceImpl:302` 对 START_PROCESS 早返回不解析 scheduleTime。

**涉及文件**：
- 前端：`Workflow.vue`、`WorkflowEditor.vue`、`SchedulerHistory.vue`、新增 `BackfillCreateModal.vue`、改写 `Backfill.vue`、删除 `ComplementModal.vue`、`api/index.ts`
- 后端：`ds_proxy.py`（端点改 410）、`backfill.py`（错误信息更详细）

**经验**：升级第三方调度系统（DS 2.x → 3.x）时，接口契约可能悄悄变。**永远不要**让 UI 出现两个做同一件事的入口 — 用户只会用第一个见到的，第二个永远收不到反馈。竞品（DataWorks/DolphinScheduler/Airflow）的共识是发起跟着工作流走，监控独立成页。

---

## [2026-05] DS 重启 2499 次 — MySQL JDBC 驱动是目录不是文件

**现象**：新服务器部署后 DS 容器反复重启（RestartCount: 2499），日志报 `Cannot load driver class: com.mysql.cj.jdbc.Driver`，`spring.datasource` bean 创建失败。

**根因**：`drivers/mysql-connector-j-8.0.33.jar` 在服务器上是个**空目录**而非 JAR 文件。rsync 时本地该路径不存在（未提交进 git），rsync 把它作为目录创建。Docker volume bind mount 把目录挂到容器内文件路径，导致 `standalone-server/mysql-connector-j-8.0.33.jar` 变成空目录，JVM classpath 找不到驱动类。

**正确做法**：
1. 删掉目录：`rm -rf /root/data-platform-mvp/drivers/mysql-connector-j-8.0.33.jar`
2. 下载真实 JAR：`curl -L "https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/8.0.33/mysql-connector-j-8.0.33.jar" -o drivers/mysql-connector-j-8.0.33.jar`
3. 重建容器（`restart` 不够，必须 `docker compose up -d --force-recreate dolphinscheduler`）

**永久方案**：把 JAR 文件提交进 git，或在 DS Dockerfile 里 `RUN curl` 下载，不依赖 volume bind mount 传入二进制文件。

**涉及文件**：`docker-compose.yml`（volumes 配置）、`drivers/mysql-connector-j-8.0.33.jar`

---

## [2026-05] DS 启动卡死 — 空数据库需要手动初始化 schema

**现象**：新服务器全新 `dolphinscheduler` 数据库（0 张表）。DS 进程启动后日志停在 `HikariPool-1 - Start completed` 之后，`AlertPluginManager: Plugin Define Table t_ds_plugin_define Not Exist`，进程不崩溃但不继续推进，健康检查 `unhealthy`，HTTP 端口始终不响应。

**根因**：DS standalone 依靠 Flyway/Spring SQL init 在启动时自动建表，但在全新空库情况下，Spring context 某个 bean（`AlertPluginManager`）在 Flyway 运行前就尝试查询 `t_ds_plugin_define` 表，抛出异常并阻塞了整个 Spring context 初始化，导致 Flyway 永远没机会执行。进程活着但 Spring 已死锁。

**正确做法**：新服务器首次部署前，手动初始化 DS 数据库：
```bash
docker exec -i dmp-mysql mysql -uroot -pDpMvp2026Secure dolphinscheduler \
  < <(docker exec dmp-ds cat /opt/dolphinscheduler/conf/sql/dolphinscheduler_mysql.sql)
# 确认 67 张表建好后再启动/重启 DS
```

**规则**：换服务器重建后，必须先手动跑一次 DS schema init，再 `docker compose up -d dolphinscheduler`。

**涉及文件**：`/opt/dolphinscheduler/conf/sql/dolphinscheduler_mysql.sql`（容器内）

---

## [2026-05] DS JVM heap 与容器 mem_limit 冲突导致卡死

**现象**：DS 镜像默认 JVM 参数 `-Xms4g -Xmx4g -Xmn2g`，在 `mem_limit: 4g` 的容器中运行，JVM 申请 4GB heap 加上 OS/metaspace 开销，总内存超过容器限制，进程不报 OOM 但完全卡死（CPU 4-5%，无新日志，不崩溃不重启）。

**正确做法**：在 DS Dockerfile 中覆盖 `/opt/dolphinscheduler/bin/jvm_args_env.sh`，把 heap 改为 `-Xms1g -Xmx2g -Xmn512m`，容器 mem_limit 改为 `3g`：
```
mem_limit: 3g     # docker-compose.yml
-Xms1g -Xmx2g    # dolphinscheduler/Dockerfile 写入 jvm_args_env.sh
```

**涉及文件**：`dolphinscheduler/Dockerfile`、`docker-compose.yml`

---

## [2026-05] 新服务器 DS 无 Project — portal 工作流 API 全返 503

**现象**：DS 健康检查通过后，portal 的 `/api/ds/instances`、工作流发布/运行等所有涉及 DS 的接口仍返回 503。无报错日志，只有 `DS 项目不可用`。

**根因**：DS standalone 镜像首次启动后数据库里没有任何 Project。`DSClient._discover_project()` 调 `GET /projects` 得到空 `totalList`，返回 `None`，所有业务方法静默失败，`_project_code()` 抛 `HTTPException(503)`。

**正确做法**：新服务器 DS 启动健康后，手动创建一个默认项目（只需一次）：
```bash
docker exec dmp-ds python3 -c "
import urllib.request, urllib.parse, json
base = 'http://localhost:12345/dolphinscheduler'
data = urllib.parse.urlencode({'userName':'admin','userPassword':'dolphinscheduler123'}).encode()
sid = json.loads(urllib.request.urlopen(urllib.request.Request(base+'/login',data), timeout=10).read())['data']['sessionId']
data2 = urllib.parse.urlencode({'projectName':'data-platform-mvp','description':'默认项目'}).encode()
r = json.loads(urllib.request.urlopen(urllib.request.Request(base+'/projects',data2,{'Cookie':'sessionId='+sid}), timeout=10).read())
print('code:', r.get('code'), 'project_code:', r.get('data',{}).get('code'))
"
```

**涉及文件**：`app/core/ds_client.py` — `_discover_project()`、`ds_proxy.py` — `_project_code()`

---

## [2026-05-28] publish-as-workflow 幂等路径不同步 DS

**现象**：同步任务改了字段映射后，重新点"发布为工作流"，Portal 组件的 config_json 更新了，但 DS 侧还是旧的 DataX 配置。跑出来的数据用的是旧字段映射。

**根因**：`sync_tasks.py` 的 `publish_as_workflow` 幂等路径（已存在组件时）只更新了 `existing_comp.config_json` 就 return，没有重新调 DS 的 `update_process_definition` + `release_process_definition`。

**正确做法**：幂等路径也要通过 `WorkflowPublisher.publish(wf)` 重新同步到 DS。`WorkflowPublisher._save_or_update` 会自动判断是创建还是更新（通过 `wf.ds_process_code` 是否存在）。

**同时修复的问题**：
- 首次创建路径引用了不存在的 `_sync_to_ds`，改为使用 `WorkflowPublisher`
- `POST /sync-tasks/{id}/run` 从 subprocess 直接执行改为走 DS 调度

**涉及文件**：`portal/backend/app/api/sync_tasks.py`、`portal/frontend/src/components/SyncTaskCanvas.vue`

