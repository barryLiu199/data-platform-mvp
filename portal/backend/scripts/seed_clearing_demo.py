"""金融清算演示项目种子脚本 — 项目名「演示」

通过 Portal HTTP API 构建一条完整可演示的数据链路：

  数据源(清算库) → 业务表+数据(ODS/DIM/DW/ADS) → 组件(SQL/Python/Shell/存储过程)
  → 工作流(DAG) → 质量规则+检查结果 → 词根 → 表级/字段级血缘 → 数据目录(自动)

跑法（本机指向服务器）:
    PORTAL_BASE_URL=http://47.92.236.44 \
    PORTAL_ADMIN_PASSWORD=xxx \
    MYSQL_ROOT_PASSWORD=xxx \
    python3 portal/backend/scripts/seed_clearing_demo.py

特性：幂等（按名称查重，存在即跳过），不删除任何已有数据。
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = os.environ.get("PORTAL_BASE_URL", "http://localhost")
ADMIN_PASSWORD = os.environ.get("PORTAL_ADMIN_PASSWORD", "admin123")
MYSQL_PASSWORD = os.environ.get("MYSQL_ROOT_PASSWORD", "")

DEMO_DB = "clearing_demo"
DS_NAME = "演示_清算库"
PROJECT_NAME = "演示"
PROJECT_CODE = "demo_clearing"
WF_NAME = "演示_金融清算日终批处理"

random.seed(20260611)


# ───────────────────────── HTTP helpers ─────────────────────────

def call(method: str, path: str, token: str | None = None, body: dict | None = None,
         quiet: bool = False) -> dict:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        if not quiet:
            print(f"  ✗ {method} {path} → {e.code} {body_text[:300]}")
        return {"_error": e.code, "_body": body_text}


def login() -> str:
    r = call("POST", "/api/auth/login", body={"username": "admin", "password": ADMIN_PASSWORD})
    if "access_token" not in r:
        print("登录失败，请检查 PORTAL_ADMIN_PASSWORD")
        sys.exit(1)
    return r["access_token"]


def run_sql(token: str, ds_id: int, sql: str, label: str = "") -> dict:
    r = call("POST", "/api/components/run-sql", token,
             body={"datasource_id": ds_id, "sql": sql})
    if "_error" in r:
        print(f"  ✗ SQL 失败 [{label}]")
    return r


# ───────────────────────── 1) 项目 ─────────────────────────

def ensure_project(token: str) -> int:
    print("\n=== 1) 项目「演示」===")
    items = call("GET", "/api/projects", token).get("items", [])
    for p in items:
        if p.get("name") == PROJECT_NAME:
            print(f"  ↩ 已存在 id={p['id']}")
            return p["id"]
    r = call("POST", "/api/projects", token, body={
        "name": PROJECT_NAME,
        "code": PROJECT_CODE,
        "description": "金融清算全链路演示项目：交易→清算→结算→汇总报表",
    })
    print(f"  ✓ 创建 id={r.get('id')}")
    return r["id"]


# ───────────────────────── 2) 数据源 + 库 ─────────────────────────

def ensure_datasource(token: str) -> int:
    print("\n=== 2) 数据源「演示_清算库」===")
    items = call("GET", "/api/datasources?page=1&page_size=100", token).get("items", [])
    for d in items:
        if d.get("name") == DS_NAME:
            print(f"  ↩ 已存在 id={d['id']}")
            return d["id"]

    # 先借已有 mysql 数据源（或临时建一个指向 portal_db 的）来 CREATE DATABASE
    bootstrap_id = None
    for d in items:
        if (d.get("type") == "mysql") and d.get("host") in ("mysql", "localhost", "127.0.0.1"):
            bootstrap_id = d["id"]
            break
    created_bootstrap = False
    if bootstrap_id is None:
        r = call("POST", "/api/datasources", token, body={
            "name": "__bootstrap_tmp", "type": "mysql", "host": "mysql", "port": 3306,
            "database_name": "portal_db", "username": "root", "password": MYSQL_PASSWORD,
            "description": "临时引导数据源（脚本自动删除）",
        })
        bootstrap_id = r.get("id")
        created_bootstrap = True
    run_sql(token, bootstrap_id,
            f"CREATE DATABASE IF NOT EXISTS {DEMO_DB} DEFAULT CHARACTER SET utf8mb4",
            "create database")
    if created_bootstrap:
        call("DELETE", f"/api/datasources/{bootstrap_id}", token, quiet=True)

    r = call("POST", "/api/datasources", token, body={
        "name": DS_NAME, "type": "mysql", "host": "mysql", "port": 3306,
        "database_name": DEMO_DB, "username": "root", "password": MYSQL_PASSWORD,
        "description": "金融清算演示库（交易流水/商户/清算明细/日报）",
    })
    print(f"  ✓ 创建 id={r.get('id')}")
    return r["id"]


# ───────────────────────── 3) 建表 + 数据 ─────────────────────────

DDL = {
    "ods_pay_txn": """
CREATE TABLE IF NOT EXISTS ods_pay_txn (
  txn_id VARCHAR(32) NOT NULL COMMENT '交易流水号',
  txn_date DATE NOT NULL COMMENT '交易日期',
  txn_time DATETIME NOT NULL COMMENT '交易时间',
  mer_id VARCHAR(16) NOT NULL COMMENT '商户号',
  chnl_code VARCHAR(16) NOT NULL COMMENT '支付渠道 ALIPAY/WECHAT/UNIONPAY/BANK',
  card_no VARCHAR(32) COMMENT '卡号(脱敏)',
  txn_amt DECIMAL(16,2) NOT NULL COMMENT '交易金额',
  fee_amt DECIMAL(16,2) NOT NULL DEFAULT 0 COMMENT '手续费',
  txn_status VARCHAR(16) NOT NULL COMMENT 'SUCCESS/FAILED/REFUND',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (txn_id)
) COMMENT='ODS 支付交易流水'""",
    "ods_mer_info": """
CREATE TABLE IF NOT EXISTS ods_mer_info (
  mer_id VARCHAR(16) NOT NULL COMMENT '商户号',
  mer_name VARCHAR(128) NOT NULL COMMENT '商户名称',
  mer_type VARCHAR(32) NOT NULL COMMENT '商户类型',
  settle_acct_no VARCHAR(32) COMMENT '结算账号',
  settle_bank VARCHAR(64) COMMENT '结算银行',
  contact_phone VARCHAR(20) COMMENT '联系电话',
  status VARCHAR(8) NOT NULL DEFAULT 'NORMAL' COMMENT 'NORMAL/FROZEN',
  PRIMARY KEY (mer_id)
) COMMENT='ODS 商户信息'""",
    "dim_merchant": """
CREATE TABLE IF NOT EXISTS dim_merchant (
  mer_id VARCHAR(16) NOT NULL COMMENT '商户号',
  mer_name VARCHAR(128) NOT NULL COMMENT '商户名称',
  mer_type VARCHAR(32) NOT NULL COMMENT '商户类型',
  settle_acct_no VARCHAR(32) COMMENT '结算账号',
  settle_bank VARCHAR(64) COMMENT '结算银行',
  status VARCHAR(8) NOT NULL COMMENT '状态',
  etl_date DATE COMMENT 'ETL 日期',
  PRIMARY KEY (mer_id)
) COMMENT='DIM 商户维表'""",
    "dw_clearing_detail": """
CREATE TABLE IF NOT EXISTS dw_clearing_detail (
  clearing_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '清算明细ID',
  txn_id VARCHAR(32) NOT NULL COMMENT '交易流水号',
  txn_date DATE NOT NULL COMMENT '交易日期',
  mer_id VARCHAR(16) NOT NULL COMMENT '商户号',
  mer_name VARCHAR(128) COMMENT '商户名称',
  chnl_code VARCHAR(16) COMMENT '支付渠道',
  txn_amt DECIMAL(16,2) NOT NULL COMMENT '交易金额',
  fee_amt DECIMAL(16,2) NOT NULL COMMENT '手续费',
  settle_amt DECIMAL(16,2) NOT NULL COMMENT '结算金额=交易-手续费',
  txn_status VARCHAR(16) COMMENT '交易状态',
  etl_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'ETL 时间',
  PRIMARY KEY (clearing_id),
  UNIQUE KEY uk_txn (txn_id)
) COMMENT='DW 清算明细'""",
    "ads_clearing_daily": """
CREATE TABLE IF NOT EXISTS ads_clearing_daily (
  report_date DATE NOT NULL COMMENT '报表日期',
  mer_id VARCHAR(16) NOT NULL COMMENT '商户号',
  mer_name VARCHAR(128) COMMENT '商户名称',
  txn_cnt INT NOT NULL DEFAULT 0 COMMENT '交易笔数',
  total_txn_amt DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '交易总额',
  total_fee_amt DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '手续费总额',
  total_settle_amt DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '结算总额',
  etl_time DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (report_date, mer_id)
) COMMENT='ADS 商户日清算汇总'""",
    "clearing_settle_log": """
CREATE TABLE IF NOT EXISTS clearing_settle_log (
  id BIGINT NOT NULL AUTO_INCREMENT,
  settle_date DATE NOT NULL COMMENT '结算日期',
  mer_cnt INT COMMENT '结算商户数',
  total_amt DECIMAL(18,2) COMMENT '结算总金额',
  status VARCHAR(16) COMMENT 'DONE/FAILED',
  remark VARCHAR(255),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) COMMENT='日终结算日志（存储过程写入）'""",
}

MERCHANTS = [
    ("M10000001", "盛世百货连锁", "零售"), ("M10000002", "云端餐饮集团", "餐饮"),
    ("M10000003", "极速出行科技", "交通出行"), ("M10000004", "安康大药房", "医药"),
    ("M10000005", "星辰影院", "文娱"), ("M10000006", "优品生鲜超市", "零售"),
    ("M10000007", "环球旅行社", "旅游"), ("M10000008", "智慧教育在线", "教育"),
    ("M10000009", "悦动健身", "体育"), ("M10000010", "都市便利店", "零售"),
]
CHANNELS = ["ALIPAY", "WECHAT", "UNIONPAY", "BANK"]
FEE_RATE = {"ALIPAY": 0.006, "WECHAT": 0.006, "UNIONPAY": 0.008, "BANK": 0.01}


def seed_tables(token: str, ds_id: int):
    print("\n=== 3) 建表 + 灌数据 ===")
    for name, ddl in DDL.items():
        run_sql(token, ds_id, ddl, f"create {name}")
        print(f"  ✓ 表 {name}")

    cnt = run_sql(token, ds_id, "SELECT COUNT(*) FROM ods_pay_txn", "count")
    if cnt.get("rows") and cnt["rows"][0][0] and int(cnt["rows"][0][0]) > 0:
        print("  ↩ ods_pay_txn 已有数据，跳过灌数")
        return

    # 商户
    rows = []
    for mid, mname, mtype in MERCHANTS:
        rows.append(
            f"('{mid}','{mname}','{mtype}','62220000{mid[-4:]}','招商银行','138{random.randint(10000000, 99999999)}','NORMAL')"
        )
    run_sql(token, ds_id,
            "INSERT IGNORE INTO ods_mer_info (mer_id,mer_name,mer_type,settle_acct_no,settle_bank,contact_phone,status) VALUES "
            + ",".join(rows), "merchants")
    print(f"  ✓ ods_mer_info {len(rows)} 行")

    # 交易流水：近 3 天每天 ~40 笔，约 12% card_no 为 NULL（供空值率规则演示）
    txn_rows = []
    seq = 1
    for d_off in (2, 1, 0):
        txn_date = date.today() - timedelta(days=d_off)
        for _ in range(40):
            mid = random.choice(MERCHANTS)[0]
            chnl = random.choice(CHANNELS)
            amt = round(random.uniform(10, 50000), 2)
            fee = round(amt * FEE_RATE[chnl], 2)
            status = random.choices(["SUCCESS", "FAILED", "REFUND"], weights=[88, 7, 5])[0]
            hh, mm, ss = random.randint(8, 22), random.randint(0, 59), random.randint(0, 59)
            card = "NULL" if random.random() < 0.12 else f"'62258888****{random.randint(1000, 9999)}'"
            txn_id = f"T{txn_date.strftime('%Y%m%d')}{seq:06d}"
            seq += 1
            txn_rows.append(
                f"('{txn_id}','{txn_date}','{txn_date} {hh:02d}:{mm:02d}:{ss:02d}','{mid}','{chnl}',{card},{amt},{fee},'{status}')"
            )
    run_sql(token, ds_id,
            "INSERT IGNORE INTO ods_pay_txn (txn_id,txn_date,txn_time,mer_id,chnl_code,card_no,txn_amt,fee_amt,txn_status) VALUES "
            + ",".join(txn_rows), "transactions")
    print(f"  ✓ ods_pay_txn {len(txn_rows)} 行（近 3 天）")

    # 存储过程：日终结算
    run_sql(token, ds_id, "DROP PROCEDURE IF EXISTS proc_daily_settle", "drop proc")
    run_sql(token, ds_id, """
CREATE PROCEDURE proc_daily_settle()
BEGIN
  INSERT INTO clearing_settle_log (settle_date, mer_cnt, total_amt, status, remark)
  SELECT CURDATE(),
         COUNT(DISTINCT mer_id),
         IFNULL(SUM(settle_amt), 0),
         'DONE',
         CONCAT('日终结算完成, 明细 ', COUNT(*), ' 笔')
  FROM dw_clearing_detail
  WHERE txn_date = CURDATE() AND txn_status = 'SUCCESS';
END""", "create proc")
    print("  ✓ 存储过程 proc_daily_settle")


# ───────────────────────── 4) 组件 ─────────────────────────

SQL_DIM_LOAD = """-- DIM 商户维表加载：从 ODS 商户信息全量刷新
INSERT INTO dim_merchant (mer_id, mer_name, mer_type, settle_acct_no, settle_bank, status, etl_date)
SELECT mer_id, mer_name, mer_type, settle_acct_no, settle_bank, status, CURDATE()
FROM ods_mer_info
ON DUPLICATE KEY UPDATE
  mer_name = VALUES(mer_name),
  mer_type = VALUES(mer_type),
  settle_acct_no = VALUES(settle_acct_no),
  settle_bank = VALUES(settle_bank),
  status = VALUES(status),
  etl_date = VALUES(etl_date)"""

SQL_DW_CLEARING = """-- DW 清算明细加工：交易流水 JOIN 商户维表，计算结算金额
INSERT IGNORE INTO dw_clearing_detail
  (txn_id, txn_date, mer_id, mer_name, chnl_code, txn_amt, fee_amt, settle_amt, txn_status)
SELECT
  t.txn_id,
  t.txn_date,
  t.mer_id,
  m.mer_name,
  t.chnl_code,
  t.txn_amt,
  t.fee_amt,
  t.txn_amt - t.fee_amt AS settle_amt,
  t.txn_status
FROM ods_pay_txn t
JOIN dim_merchant m ON t.mer_id = m.mer_id
WHERE t.txn_status IN ('SUCCESS', 'REFUND')"""

SQL_ADS_DAILY = """-- ADS 商户日清算汇总
INSERT INTO ads_clearing_daily
  (report_date, mer_id, mer_name, txn_cnt, total_txn_amt, total_fee_amt, total_settle_amt)
SELECT
  txn_date,
  mer_id,
  mer_name,
  COUNT(*) AS txn_cnt,
  SUM(txn_amt) AS total_txn_amt,
  SUM(fee_amt) AS total_fee_amt,
  SUM(settle_amt) AS total_settle_amt
FROM dw_clearing_detail
WHERE txn_status = 'SUCCESS'
GROUP BY txn_date, mer_id, mer_name
ON DUPLICATE KEY UPDATE
  txn_cnt = VALUES(txn_cnt),
  total_txn_amt = VALUES(total_txn_amt),
  total_fee_amt = VALUES(total_fee_amt),
  total_settle_amt = VALUES(total_settle_amt)"""

SQL_CALL_PROC = """-- 存储过程调度：日终结算（写入 clearing_settle_log）
CALL proc_daily_settle()"""

PY_RECON = '''# 清算对账校验：核对 ODS 与 DW 金额一致性（演示脚本）
import datetime

print("[对账] 开始执行清算对账校验", datetime.datetime.now())
print("[对账] 规则1: ODS 成功交易金额 == DW 清算明细金额 ... PASS")
print("[对账] 规则2: DW 结算金额 = 交易金额 - 手续费 ... PASS")
print("[对账] 规则3: ADS 日汇总与 DW 明细聚合一致 ... PASS")
print("[对账] 全部校验通过", datetime.datetime.now())
'''

SH_ARCHIVE = '''# 清算文件归档：打包当日清算结果（演示脚本）
echo "[归档] 开始归档 $(date '+%Y-%m-%d') 清算文件"
echo "[归档] 生成结算文件 settle_$(date +%Y%m%d).csv"
echo "[归档] 上传至清算文件服务器 ... done"
echo "[归档] 归档完成 $(date)"
'''


def ensure_components(token: str, ds_id: int) -> dict:
    print("\n=== 4) 组件（SQL/Python/Shell/存储过程）===")
    existing = {c["name"]: c for c in
                call("GET", "/api/components?page=1&page_size=200", token).get("items", [])}

    defs = [
        {"name": "演示_dim_商户维表加载", "type": "sql",
         "description": "ODS 商户信息 → DIM 商户维表（全量刷新）",
         "config_json": {"sql": SQL_DIM_LOAD, "timeout": 300, "datasource_id": ds_id}},
        {"name": "演示_dw_清算明细加工", "type": "sql",
         "description": "交易流水 JOIN 商户维表生成清算明细，计算结算金额",
         "config_json": {"sql": SQL_DW_CLEARING, "timeout": 600, "datasource_id": ds_id}},
        {"name": "演示_ads_日清算汇总", "type": "sql",
         "description": "清算明细按商户/日期汇总生成日报",
         "config_json": {"sql": SQL_ADS_DAILY, "timeout": 600, "datasource_id": ds_id}},
        {"name": "演示_proc_日终结算", "type": "sql",
         "description": "存储过程调度：CALL proc_daily_settle() 执行日终结算",
         "config_json": {"sql": SQL_CALL_PROC, "timeout": 600, "datasource_id": ds_id}},
        {"name": "演示_py_清算对账校验", "type": "python",
         "description": "Python 对账：核对 ODS/DW/ADS 三层金额一致性",
         "config_json": {"script": PY_RECON, "timeout": 300}},
        {"name": "演示_sh_清算文件归档", "type": "shell",
         "description": "Shell 归档：打包结算文件并上传",
         "config_json": {"script": SH_ARCHIVE, "timeout": 120}},
    ]

    out = {}
    for d in defs:
        if d["name"] in existing:
            c = existing[d["name"]]
            out[d["name"]] = c["id"]
            print(f"  ↩ 已存在 {d['name']} id={c['id']}")
            if c.get("status") != "online":
                call("POST", f"/api/components/{c['id']}/quick-publish", token, quiet=True)
            continue
        r = call("POST", "/api/components", token, body=d)
        if "id" not in r:
            continue
        cid = r["id"]
        out[d["name"]] = cid
        call("POST", f"/api/components/{cid}/quick-publish", token)
        print(f"  ✓ {d['type']:<7} id={cid} {d['name']} → online")
    return out


# ───────────────────────── 5) 工作流 ─────────────────────────

def ensure_workflow(token: str, project_id: int, comp: dict) -> int | None:
    print("\n=== 5) 工作流（DAG）===")
    items = call("GET", "/api/workflows?page=1&page_size=100", token).get("items", [])
    for w in items:
        if w.get("name") == WF_NAME:
            print(f"  ↩ 已存在 id={w['id']}")
            return w["id"]

    def node(nid, name_key, x, y, ntype):
        return {"id": nid, "component_id": comp[name_key], "name": name_key,
                "type": ntype, "position": {"x": x, "y": y}, "skip": False}

    dag = {
        "nodes": [
            node("node-1", "演示_dim_商户维表加载", 320, 60, "sql"),
            node("node-2", "演示_dw_清算明细加工", 320, 200, "sql"),
            node("node-3", "演示_ads_日清算汇总", 160, 340, "sql"),
            node("node-4", "演示_proc_日终结算", 480, 340, "sql"),
            node("node-5", "演示_py_清算对账校验", 320, 480, "python"),
            node("node-6", "演示_sh_清算文件归档", 320, 620, "shell"),
        ],
        "edges": [
            {"id": "edge-1", "source": "node-1", "target": "node-2"},
            {"id": "edge-2", "source": "node-2", "target": "node-3"},
            {"id": "edge-3", "source": "node-2", "target": "node-4"},
            {"id": "edge-4", "source": "node-3", "target": "node-5"},
            {"id": "edge-5", "source": "node-4", "target": "node-5"},
            {"id": "edge-6", "source": "node-5", "target": "node-6"},
        ],
    }
    r = call("POST", "/api/workflows", token, body={
        "name": WF_NAME,
        "description": "金融清算日终批处理：维表加载 → 清算明细 → (日报汇总 ∥ 存储过程结算) → 对账校验 → 文件归档",
        "project_id": project_id,
        "dag": dag,
        "cron_expression": "0 30 1 * * ?",
        "tags": ["演示", "金融清算", "日终批处理"],
        "priority": 1,
    })
    if "id" not in r:
        return None
    wid = r["id"]
    print(f"  ✓ 创建 id={wid}")

    t = call("POST", f"/api/workflows/{wid}/test", token)
    if "_error" in t:
        print("  ⚠ 测试失败，跳过发布（DS 可能未就绪）")
        return wid
    pub = call("POST", f"/api/workflows/{wid}/publish", token)
    if "_error" in pub:
        print("  ⚠ 发布失败（DS 可能未就绪），工作流保持 tested")
        return wid
    print(f"  ✓ 发布 ds_process_code={pub.get('ds_process_code')}")

    for i in range(2):
        rr = call("POST", f"/api/workflows/{wid}/run", token)
        ok = "_error" not in rr
        print(f"  {'▶' if ok else '✗'} 触发运行 #{i + 1}")
        time.sleep(2)
    return wid


# ───────────────────────── 6) 质量规则 + 检查 ─────────────────────────

def ensure_quality_rules(token: str, ds_id: int, wf_id: int | None):
    print("\n=== 6) 质量规则 + 检查结果 ===")
    existing = {r["name"] for r in
                call("GET", "/api/quality/rules?page=1&page_size=200", token).get("items", [])}

    rules = [
        {"name": "演示_交易流水号唯一性", "template_code": "uniqueness",
         "datasource_id": ds_id, "table_name": "ods_pay_txn", "column_name": "txn_id",
         "config": {"fields": ["txn_id"]}, "severity": "critical"},
        {"name": "演示_交易金额非空", "template_code": "not_null",
         "datasource_id": ds_id, "table_name": "ods_pay_txn", "column_name": "txn_amt",
         "config": {"field": "txn_amt"}, "severity": "critical"},
        {"name": "演示_交易金额值域0-100万", "template_code": "value_range",
         "datasource_id": ds_id, "table_name": "ods_pay_txn", "column_name": "txn_amt",
         "config": {"field": "txn_amt", "min_value": 0.01, "max_value": 1000000},
         "severity": "warning"},
        {"name": "演示_卡号空值率低于10%", "template_code": "null_rate",
         "datasource_id": ds_id, "table_name": "ods_pay_txn", "column_name": "card_no",
         "config": {"field": "card_no", "threshold_pct": 10}, "severity": "warning"},
        {"name": "演示_清算明细行数波动", "template_code": "row_count",
         "datasource_id": ds_id, "table_name": "dw_clearing_detail",
         "config": {"threshold_pct": 50}, "severity": "warning"},
        {"name": "演示_交易数据及时性", "template_code": "timeliness",
         "datasource_id": ds_id, "table_name": "ods_pay_txn",
         "config": {"date_field": "txn_date", "expected_date": "today"},
         "severity": "critical"},
        {"name": "演示_结算金额勾稽核对", "template_code": "custom_sql",
         "datasource_id": ds_id, "table_name": "dw_clearing_detail",
         "config": {
             "sql": "SELECT COUNT(*) FROM dw_clearing_detail WHERE ABS(settle_amt - (txn_amt - fee_amt)) > 0.01",
             "operator": "=", "threshold": 0,
         }, "severity": "critical"},
    ]

    rule_ids = []
    for rd in rules:
        if rd["name"] in existing:
            print(f"  ↩ 已存在 {rd['name']}")
            continue
        if wf_id:
            rd["trigger_type"] = "manual"
        r = call("POST", "/api/quality/rules", token, body=rd)
        if "id" in r:
            rule_ids.append(r["id"])
            print(f"  ✓ {rd['template_code']:<16} {rd['name']}")

    # 批量执行生成检查结果（后台任务）
    call("POST", "/api/quality/rules/batch-execute", token, body={"rule_ids": rule_ids or []})
    print("  ▶ 已提交批量检查（结果稍后生成）")


# ───────────────────────── 7) 词根 ─────────────────────────

WORD_ROOTS = [
    ("txn", "交易", "business", "支付交易相关", "txn_id, txn_amt, txn_date"),
    ("mer", "商户", "business", "商户主体", "mer_id, mer_name"),
    ("amt", "金额", "metric", "金额类指标统一后缀", "txn_amt, settle_amt, fee_amt"),
    ("fee", "手续费", "business", "渠道手续费", "fee_amt, fee_rate"),
    ("settle", "结算", "business", "清结算业务", "settle_amt, settle_acct_no"),
    ("clearing", "清算", "business", "清算业务域", "dw_clearing_detail"),
    ("chnl", "渠道", "business", "支付渠道", "chnl_code"),
    ("acct", "账户", "business", "账户/账号", "settle_acct_no"),
    ("cnt", "笔数", "metric", "计数类指标后缀", "txn_cnt"),
    ("ods", "贴源层", "technical", "数仓分层：原始贴源", "ods_pay_txn"),
    ("dim", "维表", "technical", "数仓分层：维度表", "dim_merchant"),
    ("dw", "明细层", "technical", "数仓分层：明细加工", "dw_clearing_detail"),
    ("ads", "应用层", "technical", "数仓分层：应用报表", "ads_clearing_daily"),
    ("daily", "日粒度", "technical", "按日汇总的报表后缀", "ads_clearing_daily"),
]


def ensure_word_roots(token: str):
    print("\n=== 7) 词根 ===")
    existing = {r["en"] for r in
                call("GET", "/api/word-roots?page=1&page_size=200", token).get("items", [])}
    n = 0
    for en, cn, cat, desc, ex in WORD_ROOTS:
        if en in existing:
            continue
        r = call("POST", "/api/word-roots", token, body={
            "en": en, "cn": cn, "category": cat, "description": desc, "example": ex,
        }, quiet=True)
        if "id" in r or "en" in r:
            n += 1
    print(f"  ✓ 新增 {n} 个（已存在 {len(WORD_ROOTS) - n} 个）")


# ───────────────────────── 8) 血缘刷新 ─────────────────────────

def refresh_lineage(token: str):
    print("\n=== 8) 血缘刷新（表级 + 字段级）===")
    r = call("POST", "/api/metadata/lineage/refresh", token)
    if "_error" not in r:
        print(f"  ✓ 表级血缘 edges={r.get('edges_created')} "
              f"components={r.get('components_parsed')} sync_tasks={r.get('sync_tasks_parsed')}")
        print("  ▶ 字段级血缘后台刷新中")
    # 字段级同步刷一次，保证演示时立即可见
    r2 = call("POST", "/api/metadata/lineage/refresh-columns", token, quiet=True)
    if "_error" not in r2:
        print(f"  ✓ 字段级血缘 {json.dumps(r2, ensure_ascii=False)[:200]}")


# ───────────────────────── main ─────────────────────────

def main():
    print(f"目标环境: {BASE}")
    token = login()
    print("登录成功")

    project_id = ensure_project(token)
    ds_id = ensure_datasource(token)
    seed_tables(token, ds_id)
    comp = ensure_components(token, ds_id)

    # 先把数据链路跑一遍（直接执行 SQL），保证 DW/ADS/结算日志有数据可看
    print("\n=== 4.5) 直接执行一遍数据链路（填充 DW/ADS）===")
    for label, sql in [("dim", SQL_DIM_LOAD), ("dw", SQL_DW_CLEARING),
                       ("ads", SQL_ADS_DAILY), ("proc", SQL_CALL_PROC)]:
        r = run_sql(token, ds_id, sql, label)
        if "_error" not in r:
            print(f"  ✓ {label} affected={r.get('affected', r.get('row_count'))}")

    wf_id = ensure_workflow(token, project_id, comp)
    ensure_quality_rules(token, ds_id, wf_id)
    ensure_word_roots(token)
    refresh_lineage(token)

    print("\n=== 完成 ===")
    print("前端可查看：")
    print("  · 数据源管理 → 演示_清算库")
    print("  · 数据目录   → 选「演示_清算库」看 6 张表 + 字段 + 预览")
    print("  · 组件开发   → 6 个「演示_」组件（SQL×4 含存储过程 / Python / Shell）")
    print("  · 工作流     → 演示_金融清算日终批处理（DAG 可双击节点配置）")
    print("  · 数据质量   → 7 条「演示_」规则 + 检查结果")
    print("  · 词根管理   → txn/mer/amt/settle 等 14 个词根")
    print("  · 数据血缘   → 选组件「演示_dw_清算明细加工」或表 dw_clearing_detail")


if __name__ == "__main__":
    main()
