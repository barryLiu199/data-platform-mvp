"""数据质量规则执行引擎 — 10 种模板 SQL 生成 + 统一执行流程"""
import logging
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.db_adapters import get_adapter
from app.models.datasource import DataSource
from app.models.quality import QualityRule, QualityCheckResult, QualityRuleTemplate

logger = logging.getLogger(__name__)

MAX_CROSS_TABLE_ROWS = 100_000


# ─── SQL Generators ─────────────────────────────────────────────────────────

def _gen_not_null(rule: QualityRule, config: dict) -> Tuple[str, dict]:
    """非空检查 — 返回 NULL 行数"""
    field = config["field"]
    sql = f"SELECT COUNT(*) FROM {rule.table_name} WHERE {field} IS NULL"
    return sql, {"pass_when": "eq_zero"}


def _gen_uniqueness(rule: QualityRule, config: dict) -> Tuple[str, dict]:
    """唯一性检查 — 返回重复行数"""
    fields = config["fields"]
    if isinstance(fields, list):
        field_expr = ", ".join(fields)
    else:
        field_expr = fields
    sql = (
        f"SELECT COUNT(*) - COUNT(DISTINCT {field_expr}) "
        f"FROM {rule.table_name}"
    )
    return sql, {"pass_when": "eq_zero"}


def _gen_null_rate(rule: QualityRule, config: dict) -> Tuple[str, dict]:
    """字段空值率 — 返回空值率百分比"""
    field = config["field"]
    threshold = config.get("threshold_pct", 5)
    sql = (
        f"SELECT SUM(CASE WHEN {field} IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) "
        f"FROM {rule.table_name}"
    )
    return sql, {"pass_when": "lte", "threshold": threshold}


def _gen_value_range(rule: QualityRule, config: dict) -> Tuple[str, dict]:
    """值域范围检查 — 返回越界行数"""
    field = config["field"]
    conditions = []
    if config.get("min_value") is not None:
        conditions.append(f"{field} < {config['min_value']}")
    if config.get("max_value") is not None:
        conditions.append(f"{field} > {config['max_value']}")
    if not conditions:
        conditions.append("1=0")
    where = " OR ".join(conditions)
    sql = f"SELECT COUNT(*) FROM {rule.table_name} WHERE {where}"
    return sql, {"pass_when": "eq_zero"}


def _gen_regex_match(rule: QualityRule, config: dict) -> Tuple[str, dict]:
    """正则匹配 — 返回不匹配行数"""
    field = config["field"]
    pattern = config["pattern"]
    sql = f"SELECT COUNT(*) FROM {rule.table_name} WHERE NOT ({field} REGEXP '{pattern}')"
    return sql, {"pass_when": "eq_zero"}


def _gen_row_count(rule: QualityRule, config: dict) -> Tuple[str, dict]:
    """表行数波动 — 返回当前行数，与上次比较"""
    threshold = config.get("threshold_pct", 50)
    sql = f"SELECT COUNT(*) FROM {rule.table_name}"
    return sql, {"pass_when": "row_count_volatility", "threshold": threshold}


def _gen_timeliness(rule: QualityRule, config: dict) -> Tuple[str, dict]:
    """及时性检查 — 检查目标日期是否有数据"""
    date_field = config["date_field"]
    expected = config.get("expected_date", "today")
    if expected == "today":
        expected = date.today().isoformat()
    sql = f"SELECT COUNT(*) FROM {rule.table_name} WHERE {date_field} >= '{expected}'"
    return sql, {"pass_when": "gt_zero"}


def _gen_dict_ref(rule: QualityRule, config: dict) -> Tuple[str, dict]:
    """字典引用检查 — 返回孤立记录数"""
    field = config["field"]
    dict_table = config["dict_table"]
    dict_field = config["dict_field"]
    sql = (
        f"SELECT COUNT(*) FROM {rule.table_name} a "
        f"LEFT JOIN {dict_table} b ON a.{field} = b.{dict_field} "
        f"WHERE b.{dict_field} IS NULL"
    )
    return sql, {"pass_when": "eq_zero"}


def _gen_custom_sql(rule: QualityRule, config: dict) -> Tuple[str, dict]:
    """自定义 SQL — 用户 SQL 返回单行单列数值"""
    sql = config["sql"]
    operator = config["operator"]
    threshold = config["threshold"]
    return sql, {"pass_when": "custom", "operator": operator, "threshold": threshold}


def _gen_cross_table_check(rule: QualityRule, config: dict) -> Tuple[str, dict]:
    """跨表核对 — 特殊处理，返回标记而非 SQL"""
    return "__CROSS_TABLE__", config


GENERATORS = {
    "not_null": _gen_not_null,
    "uniqueness": _gen_uniqueness,
    "null_rate": _gen_null_rate,
    "value_range": _gen_value_range,
    "regex_match": _gen_regex_match,
    "row_count": _gen_row_count,
    "timeliness": _gen_timeliness,
    "dict_ref": _gen_dict_ref,
    "custom_sql": _gen_custom_sql,
    "cross_table_check": _gen_cross_table_check,
}


# ─── Evaluation Logic ────────────────────────────────────────────────────────

def _evaluate(actual_value: float, meta: dict, rule: QualityRule, db: Session) -> str:
    """根据 meta 中的 pass_when 判定 pass/fail"""
    pw = meta["pass_when"]

    if pw == "eq_zero":
        return "pass" if actual_value == 0 else "fail"

    if pw == "gt_zero":
        return "pass" if actual_value > 0 else "fail"

    if pw == "lte":
        return "pass" if actual_value <= meta["threshold"] else "fail"

    if pw == "row_count_volatility":
        last_result = (
            db.query(QualityCheckResult)
            .filter(QualityCheckResult.rule_id == rule.id)
            .order_by(QualityCheckResult.check_date.desc())
            .first()
        )
        if not last_result or last_result.actual_value is None or last_result.actual_value == 0:
            return "pass"
        prev = last_result.actual_value
        volatility = abs(actual_value - prev) / prev * 100
        return "pass" if volatility <= meta["threshold"] else "fail"

    if pw == "custom":
        op = meta["operator"]
        threshold = meta["threshold"]
        ops = {
            "=": lambda a, t: a == t,
            "!=": lambda a, t: a != t,
            ">": lambda a, t: a > t,
            ">=": lambda a, t: a >= t,
            "<": lambda a, t: a < t,
            "<=": lambda a, t: a <= t,
        }
        fn = ops.get(op, lambda a, t: False)
        return "pass" if fn(actual_value, threshold) else "fail"

    return "error"


# ─── Cross-table Comparison ──────────────────────────────────────────────────

def _execute_cross_table(rule: QualityRule, config: dict, db: Session) -> Dict[str, Any]:
    """跨表核对：分别查两个数据源，Python 侧 merge 比较"""
    ds_a = db.query(DataSource).get(config["ds_id_a"])
    ds_b = db.query(DataSource).get(config["ds_id_b"])
    if not ds_a or not ds_b:
        return {"status": "error", "error_message": "数据源不存在"}

    join_keys = config["join_keys"]
    compare_fields = config["compare_fields"]
    tolerance = config.get("tolerance", 0)

    key_a_cols = [k["a"] for k in join_keys]
    key_b_cols = [k["b"] for k in join_keys]
    val_a_cols = [f["a"] for f in compare_fields]
    val_b_cols = [f["b"] for f in compare_fields]

    sql_a = f"SELECT {', '.join(key_a_cols + val_a_cols)} FROM {config['table_a']}"
    sql_b = f"SELECT {', '.join(key_b_cols + val_b_cols)} FROM {config['table_b']}"

    try:
        adapter_a = get_adapter(ds_a)
        conn_a = adapter_a.connect()
        try:
            cur_a = conn_a.cursor()
            cur_a.execute(sql_a)
            rows_a = cur_a.fetchmany(MAX_CROSS_TABLE_ROWS)
            cur_a.close()
        finally:
            conn_a.close()

        adapter_b = get_adapter(ds_b)
        conn_b = adapter_b.connect()
        try:
            cur_b = conn_b.cursor()
            cur_b.execute(sql_b)
            rows_b = cur_b.fetchmany(MAX_CROSS_TABLE_ROWS)
            cur_b.close()
        finally:
            conn_b.close()
    except Exception as e:
        return {"status": "error", "error_message": str(e)}

    return compare_datasets(
        rows_a, rows_b, key_a_cols, key_b_cols, val_a_cols, val_b_cols, tolerance
    )


def compare_datasets(
    rows_a: List[tuple],
    rows_b: List[tuple],
    key_a_cols: List[str],
    key_b_cols: List[str],
    val_a_cols: List[str],
    val_b_cols: List[str],
    tolerance: float = 0,
) -> Dict[str, Any]:
    """比较两个数据集，返回差异统计"""
    n_keys = len(key_a_cols)
    n_vals = len(val_a_cols)

    map_a: Dict[tuple, tuple] = {}
    for row in rows_a:
        key = tuple(row[:n_keys])
        vals = tuple(row[n_keys:n_keys + n_vals])
        map_a[key] = vals

    diff_count = 0
    missing_in_a = 0
    diff_samples: List[dict] = []

    for row in rows_b:
        key = tuple(row[:n_keys])
        vals_b = tuple(row[n_keys:n_keys + n_vals])
        vals_a = map_a.pop(key, None)
        if vals_a is None:
            missing_in_a += 1
            diff_count += 1
            if len(diff_samples) < 20:
                diff_samples.append({"key": list(key), "type": "missing_in_a"})
            continue
        for i in range(n_vals):
            a_val = vals_a[i] if vals_a[i] is not None else 0
            b_val = vals_b[i] if vals_b[i] is not None else 0
            try:
                if abs(float(a_val) - float(b_val)) > tolerance:
                    diff_count += 1
                    if len(diff_samples) < 20:
                        diff_samples.append({
                            "key": list(key),
                            "type": "value_mismatch",
                            "field_index": i,
                            "a": a_val,
                            "b": b_val,
                        })
                    break
            except (ValueError, TypeError):
                if str(a_val) != str(b_val):
                    diff_count += 1
                    if len(diff_samples) < 20:
                        diff_samples.append({
                            "key": list(key),
                            "type": "value_mismatch",
                            "field_index": i,
                            "a": str(a_val),
                            "b": str(b_val),
                        })
                    break

    missing_in_b = len(map_a)
    diff_count += missing_in_b
    for key in list(map_a.keys())[:20 - len(diff_samples)]:
        diff_samples.append({"key": list(key), "type": "missing_in_b"})

    status = "pass" if diff_count <= tolerance else "fail"
    return {
        "status": status,
        "actual_value": float(diff_count),
        "expected_value": float(tolerance),
        "detail": {
            "diff_count": diff_count,
            "missing_in_a": missing_in_a,
            "missing_in_b": missing_in_b,
            "samples": diff_samples,
        },
        "executed_sql": f"A: {len(rows_a)} rows | B: {len(rows_b)} rows",
    }


# ─── Main Execution Entry ────────────────────────────────────────────────────

def execute_rule(rule_id: int, triggered_by: str = "manual", db: Session = None) -> Dict[str, Any]:
    """执行单条质量规则，写入结果，返回结果 dict。

    线程安全：每次调用创建独立 session（除非外部传入）。
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        rule = db.query(QualityRule).get(rule_id)
        if not rule:
            return {"status": "error", "error_message": f"规则 {rule_id} 不存在"}

        if not rule.enabled:
            return {"status": "error", "error_message": f"规则 {rule_id} 已禁用"}

        gen = GENERATORS.get(rule.template_code)
        if not gen:
            return {"status": "error", "error_message": f"未知模板: {rule.template_code}"}

        start_ms = time.time()
        config = rule.config or {}

        # Cross-table is a special path
        if rule.template_code == "cross_table_check":
            result = _execute_cross_table(rule, config, db)
            duration_ms = int((time.time() - start_ms) * 1000)
            result["duration_ms"] = duration_ms
            _save_result(db, rule, result, triggered_by)
            return result

        # Standard path: generate SQL → execute → evaluate
        sql, meta = gen(rule, config)

        ds = db.query(DataSource).get(rule.datasource_id) if rule.datasource_id else None
        if not ds:
            result = {"status": "error", "error_message": "数据源未配置或不存在"}
            _save_result(db, rule, result, triggered_by)
            return result

        try:
            adapter = get_adapter(ds)
            conn = adapter.connect()
            try:
                cur = conn.cursor()
                cur.execute(sql)
                row = cur.fetchone()
                actual_value = float(row[0]) if row and row[0] is not None else 0.0
                cur.close()
            finally:
                conn.close()
        except Exception as e:
            duration_ms = int((time.time() - start_ms) * 1000)
            result = {
                "status": "error",
                "error_message": str(e),
                "executed_sql": sql,
                "duration_ms": duration_ms,
            }
            _save_result(db, rule, result, triggered_by)
            return result

        duration_ms = int((time.time() - start_ms) * 1000)
        status = _evaluate(actual_value, meta, rule, db)

        expected_value = meta.get("threshold")
        result = {
            "status": status,
            "actual_value": actual_value,
            "expected_value": expected_value,
            "executed_sql": sql,
            "duration_ms": duration_ms,
        }
        _save_result(db, rule, result, triggered_by)
        return result

    except Exception as e:
        logger.exception(f"质量规则 {rule_id} 执行异常")
        return {"status": "error", "error_message": str(e)}
    finally:
        if own_session:
            db.close()


def _save_result(db: Session, rule: QualityRule, result: Dict[str, Any], triggered_by: str):
    """UPSERT 检查结果到 quality_check_result，更新 rule 最近检查状态"""
    check_date = date.today()
    status = result.get("status", "error")

    existing = (
        db.query(QualityCheckResult)
        .filter(
            QualityCheckResult.rule_id == rule.id,
            QualityCheckResult.check_date == check_date,
        )
        .first()
    )

    if existing:
        existing.status = status
        existing.actual_value = result.get("actual_value")
        existing.expected_value = result.get("expected_value")
        existing.detail = result.get("detail")
        existing.executed_sql = result.get("executed_sql")
        existing.duration_ms = result.get("duration_ms")
        existing.error_message = result.get("error_message")
        existing.triggered_by = triggered_by
    else:
        record = QualityCheckResult(
            rule_id=rule.id,
            check_date=check_date,
            status=status,
            actual_value=result.get("actual_value"),
            expected_value=result.get("expected_value"),
            detail=result.get("detail"),
            executed_sql=result.get("executed_sql"),
            duration_ms=result.get("duration_ms"),
            error_message=result.get("error_message"),
            triggered_by=triggered_by,
        )
        db.add(record)

    rule.last_check_time = datetime.utcnow()
    rule.last_check_status = status
    db.commit()


def preview_sql(rule_id: int, db: Session) -> Dict[str, Any]:
    """预览规则将要执行的 SQL（不实际执行）"""
    rule = db.query(QualityRule).get(rule_id)
    if not rule:
        return {"error": f"规则 {rule_id} 不存在"}

    gen = GENERATORS.get(rule.template_code)
    if not gen:
        return {"error": f"未知模板: {rule.template_code}"}

    config = rule.config or {}
    if rule.template_code == "cross_table_check":
        join_keys = config.get("join_keys", [])
        compare_fields = config.get("compare_fields", [])
        key_a_cols = [k["a"] for k in join_keys]
        val_a_cols = [f["a"] for f in compare_fields]
        key_b_cols = [k["b"] for k in join_keys]
        val_b_cols = [f["b"] for f in compare_fields]
        sql_a = f"SELECT {', '.join(key_a_cols + val_a_cols)} FROM {config.get('table_a', '?')}"
        sql_b = f"SELECT {', '.join(key_b_cols + val_b_cols)} FROM {config.get('table_b', '?')}"
        return {"sql": f"-- 数据源A:\n{sql_a}\n\n-- 数据源B:\n{sql_b}"}

    sql, _ = gen(rule, config)
    return {"sql": sql}
