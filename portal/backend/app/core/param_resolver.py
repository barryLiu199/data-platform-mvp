"""调度日期参数解析器

将 SQL / DataX where_clause / 存储过程参数中的 ${bizdate} 等占位符
按运行日期替换为字符串。

设计：
- 系统参数 SYSTEM_PARAMS：固定 6 个日期类占位符
- 用户自定义参数 extra：通过工作流参数面板传入，可覆盖系统参数
- 未注册的 ${xxx} 保持原样，便于上层在日志/UI 中诊断缺失参数
"""
from datetime import date, timedelta
from typing import Callable, Dict, Optional


def _premonth(d: date) -> str:
    """上个月的 YYYY-MM（跨年安全）"""
    first_day_this_month = d.replace(day=1)
    last_day_prev_month = first_day_this_month - timedelta(days=1)
    return last_day_prev_month.strftime("%Y-%m")


SYSTEM_PARAMS: Dict[str, Callable[[date], str]] = {
    "bizdate":   lambda d: d.strftime("%Y-%m-%d"),
    "bizdatecn": lambda d: d.strftime("%Y%m%d"),
    "bizmonth":  lambda d: d.strftime("%Y-%m"),
    "bizyear":   lambda d: d.strftime("%Y"),
    "yesterday": lambda d: (d - timedelta(days=1)).strftime("%Y-%m-%d"),
    "premonth":  _premonth,
}


def resolve(template: str, run_date: date, extra: Optional[Dict[str, str]] = None) -> str:
    """将 template 中所有 ${key} 替换为对应值。

    Args:
        template: 含 ${key} 占位符的字符串
        run_date: 运行日期，作为系统参数计算的基准
        extra: 工作流自定义参数字典，key 与系统参数冲突时 extra 优先

    Returns:
        替换后的字符串。未注册的占位符保持原样。
    """
    if not template:
        return template
    resolved: Dict[str, str] = {k: f(run_date) for k, f in SYSTEM_PARAMS.items()}
    if extra:
        resolved.update({k: str(v) for k, v in extra.items()})
    out = template
    for k, v in resolved.items():
        out = out.replace(f"${{{k}}}", v)
    return out
