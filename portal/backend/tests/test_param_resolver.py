"""调度日期参数解析单元测试 — 模式 A：纯函数，无 DB / Mock 依赖"""
from datetime import date

from app.core.param_resolver import resolve, SYSTEM_PARAMS


def test_bizdate_format():
    """${bizdate} 应替换为 YYYY-MM-DD"""
    out = resolve("select * from t where dt='${bizdate}'", date(2025, 1, 15))
    assert out == "select * from t where dt='2025-01-15'"


def test_bizdatecn_format():
    """${bizdatecn} 应替换为 YYYYMMDD（无分隔符）"""
    out = resolve("/data/${bizdatecn}/part-0", date(2025, 1, 15))
    assert out == "/data/20250115/part-0"


def test_bizmonth_and_bizyear_format():
    """${bizmonth} 为 YYYY-MM, ${bizyear} 为 YYYY"""
    out = resolve("m=${bizmonth},y=${bizyear}", date(2025, 1, 15))
    assert out == "m=2025-01,y=2025"


def test_yesterday():
    """${yesterday} 应为 run_date 前一天"""
    out = resolve("dt='${yesterday}'", date(2025, 1, 1))
    assert out == "dt='2024-12-31'"


def test_premonth():
    """${premonth} 应为上个月的 YYYY-MM"""
    out = resolve("month=${premonth}", date(2025, 3, 15))
    assert out == "month=2025-02"
    # 跨年
    out2 = resolve("month=${premonth}", date(2025, 1, 10))
    assert out2 == "month=2024-12"


def test_custom_param_overrides_system():
    """自定义参数（extra）的 key 与系统参数冲突时，自定义优先"""
    out = resolve("dt='${bizdate}'", date(2025, 1, 15), extra={"bizdate": "OVERRIDE"})
    assert out == "dt='OVERRIDE'"


def test_custom_param_added():
    """自定义参数 key 不与系统冲突时正常注入"""
    out = resolve("name='${env}'", date(2025, 1, 15), extra={"env": "prod"})
    assert out == "name='prod'"


def test_no_placeholder_unchanged():
    """模板里没有占位符，应原样返回"""
    sql = "select count(*) from orders"
    assert resolve(sql, date(2025, 1, 15)) == sql


def test_multiple_occurrences_all_replaced():
    """同一占位符出现多次，全部替换"""
    out = resolve(
        "insert into log values('${bizdate}','${bizdate}')",
        date(2025, 1, 15),
    )
    assert out == "insert into log values('2025-01-15','2025-01-15')"


def test_unknown_placeholder_left_as_is():
    """未注册的占位符保持原样（不抛错），便于上层做诊断"""
    out = resolve("x=${unknown_var}", date(2025, 1, 15))
    assert out == "x=${unknown_var}"


def test_system_params_keys_present():
    """系统参数必须包含约定的 6 个 key"""
    expected = {"bizdate", "bizdatecn", "bizmonth", "bizyear", "yesterday", "premonth"}
    assert expected.issubset(set(SYSTEM_PARAMS.keys()))
