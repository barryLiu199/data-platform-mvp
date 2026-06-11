"""安全回归：每个生成器对注入向量必须抛 IdentifierError，
即使没抛错也不能让恶意载荷出现在 SQL 字符串里。

注入向量针对 quality_engine 历来的拼接点：
- rule.table_name
- config["field"] / fields[*]
- config["dict_table"] / config["dict_field"]
- config["date_field"]
- config["pattern"]（这条走参数化，不抛错但必须不出现在 SQL 文本里）
"""
import pytest
from unittest.mock import MagicMock

from app.core.quality_engine import (
    _gen_not_null, _gen_uniqueness, _gen_null_rate, _gen_value_range,
    _gen_regex_match, _gen_row_count, _gen_timeliness, _gen_dict_ref,
)
from app.core.validators import IdentifierError
from app.models.quality import QualityRule


def _rule(table="orders", **kw):
    r = MagicMock(spec=QualityRule)
    r.id = 1
    r.table_name = table
    r.template_code = kw.get("template_code", "not_null")
    r.datasource_id = 1
    r.config = {}
    r.enabled = True
    return r


# 经典注入向量
INJECT_VECTORS = [
    "t WHERE 1=1",
    "t; DROP TABLE users--",
    "t UNION SELECT password FROM sys_user",
    "users` UNION SELECT 1,2--",
    'users" OR "1"="1',
    "users ]; --",
    "a.b.c",          # 多级点号（绕过 schema.table）
    "a..b",
    "a b",
    "1foo",           # 数字开头
    "",               # 空
    "; SELECT pg_sleep(10)",
    "/* nasty */",
    "evil`drop`",
    "你好",            # 非 ASCII
]


# ─── table_name 注入 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("evil", INJECT_VECTORS)
def test_not_null_rejects_evil_table(evil):
    with pytest.raises(IdentifierError):
        _gen_not_null(_rule(table=evil), {"field": "x"}, "mysql")


@pytest.mark.parametrize("evil", INJECT_VECTORS)
def test_row_count_rejects_evil_table(evil):
    with pytest.raises(IdentifierError):
        _gen_row_count(_rule(table=evil), {}, "mysql")


# ─── config["field"] / fields[*] 注入 ────────────────────────────────────

@pytest.mark.parametrize("evil", INJECT_VECTORS)
def test_not_null_rejects_evil_field(evil):
    with pytest.raises(IdentifierError):
        _gen_not_null(_rule(), {"field": evil}, "mysql")


@pytest.mark.parametrize("evil", INJECT_VECTORS)
def test_uniqueness_rejects_evil_field_in_list(evil):
    with pytest.raises(IdentifierError):
        _gen_uniqueness(_rule(), {"fields": ["legit_col", evil]}, "mysql")


@pytest.mark.parametrize("evil", INJECT_VECTORS)
def test_null_rate_rejects_evil_field(evil):
    with pytest.raises(IdentifierError):
        _gen_null_rate(_rule(), {"field": evil, "threshold_pct": 5}, "mysql")


@pytest.mark.parametrize("evil", INJECT_VECTORS)
def test_value_range_rejects_evil_field(evil):
    with pytest.raises(IdentifierError):
        _gen_value_range(
            _rule(), {"field": evil, "min_value": 0, "max_value": 100}, "mysql"
        )


# ─── dict_ref 4 个标识符 ────────────────────────────────────────────────

@pytest.mark.parametrize("which", ["field", "dict_table", "dict_field"])
def test_dict_ref_rejects_evil_each_field(which):
    config = {
        "field": "ok_field",
        "dict_table": "ok_dict",
        "dict_field": "ok_code",
    }
    config[which] = "evil; --"
    with pytest.raises(IdentifierError):
        _gen_dict_ref(_rule(), config, "mysql")


# ─── timeliness date_field 注入 ─────────────────────────────────────────

@pytest.mark.parametrize("evil", INJECT_VECTORS)
def test_timeliness_rejects_evil_date_field(evil):
    with pytest.raises(IdentifierError):
        _gen_timeliness(
            _rule(), {"date_field": evil, "expected_date": "2026-01-01"}, "mysql"
        )


# ─── regex pattern: 参数化路径，必须不抛错但不能出现在 SQL 字符串里 ──────

EVIL_PATTERNS = [
    "'; DROP TABLE users; --",
    "' OR '1'='1",
    "x') UNION SELECT password FROM sys_user --",
    "%' OR 1=1 --",
]


@pytest.mark.parametrize("evil", EVIL_PATTERNS)
def test_regex_pattern_parameterized_not_in_sql(evil):
    """pattern 走 %s 绑定 — 即使是恶意 SQL 也只是字面量"""
    sql, params, _ = _gen_regex_match(
        _rule(), {"field": "x", "pattern": evil}, "mysql"
    )
    assert evil not in sql
    assert "DROP" not in sql.upper().split("REGEXP")[0]
    assert params == (evil,)


# ─── timeliness expected_date: 参数化，恶意值不能出现在 SQL 里 ──────────

@pytest.mark.parametrize("evil", [
    "2026-01-01' OR '1'='1",
    "today'; DROP TABLE x;--",
])
def test_timeliness_expected_date_parameterized(evil):
    sql, params, _ = _gen_timeliness(
        _rule(), {"date_field": "dt", "expected_date": evil}, "mysql"
    )
    assert evil not in sql
    assert params == (evil,)


# ─── value_range min/max: 参数化，恶意字符串不能出现在 SQL 里 ───────────

def test_value_range_min_max_parameterized():
    """min/max 走 %s — 即使传了恶意字符串（比如类型错误），也只是字面量"""
    evil = "0; DROP TABLE x; --"
    sql, params, _ = _gen_value_range(
        _rule(), {"field": "x", "min_value": evil}, "mysql"
    )
    assert evil not in sql
    assert "%s" in sql
    assert params == (evil,)
