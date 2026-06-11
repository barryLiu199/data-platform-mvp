"""SQL 标识符白名单校验 + 方言引号包裹

为什么需要这个模块：
1. SQL 标识符（表名/列名）无法通过 DB 驱动 bind params 参数化，只能用白名单 + 引号双重防御
2. 项目里原本散落了多处独立写的正则（datax_builder / hive adapter /
   metadata.py 的 list_columns / preview / quality 引擎），质量不一，统一收口于此
3. 引号包裹时必须转义引号字符自身（双重防御），仅靠白名单不够

注意：lineage_service 的 _is_valid_table 不在收口范围 — 它过滤的是 SQL 解析器
产出的表名（允许 catalog.db.table 多级点号），不拼接 SQL，不是注入防线。
"""
from __future__ import annotations

import re
from typing import Optional


class IdentifierError(ValueError):
    """非法 SQL 标识符（表名/列名等）。调用方应包成 HTTPException(422)"""

    def __init__(self, message: str, *, field: Optional[str] = None, value: Optional[str] = None):
        self.field = field
        self.value = value
        super().__init__(message)


_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$")
# 允许：单段标识符 a / a_b / A1 / _x；最多一个点号的 schema.table 形式
# 拒绝：空格、引号、分号、注释符、多级点号、emoji、超长

_MAX_IDENT_LEN = 256


def validate_sql_identifier(value: str, *, field: str = "identifier") -> str:
    """白名单校验。非法直接抛 IdentifierError。

    合法：单段 [A-Za-z_][A-Za-z0-9_]*（首字符必须字母/下划线）
          可选一个点号分隔的 schema.table 两段形式
    长度上限 256（含点号）

    返回原值（透传），方便链式：`quote_identifier(d, validate_sql_identifier(x))`
    """
    if value is None:
        raise IdentifierError(f"{field} 不能为空", field=field, value=value)
    if not isinstance(value, str):
        raise IdentifierError(f"{field} 必须为字符串", field=field, value=str(value))
    if not value:
        raise IdentifierError(f"{field} 不能为空", field=field, value=value)
    if len(value) > _MAX_IDENT_LEN:
        raise IdentifierError(
            f"{field} 长度超过 {_MAX_IDENT_LEN}", field=field, value=value[:32] + "..."
        )
    if not _IDENT_RE.match(value):
        raise IdentifierError(
            f"{field} 格式非法：仅支持字母/数字/下划线，可选 schema.table 两段形式",
            field=field,
            value=value,
        )
    return value


_DIALECT_QUOTE = {
    # quote_char, escape_pair（出现在标识符内部需要转义为这串）
    "mysql": ("`", "``"),
    "clickhouse": ("`", "``"),
    "postgresql": ('"', '""'),
    "oracle": ('"', '""'),
    "sqlserver": ("]", "]]"),  # 实际包裹字符是 [ 和 ]，仅 ] 需要转义为 ]]
    "hive": ("`", "``"),
}


def quote_identifier(dialect: str, ident: str) -> str:
    """按方言加引号；对引号字符自身做转义（双重防御）。

    支持点号 schema.table 形式：自动按点号 split 后逐段引用，
    例如 mysql 下 `db.tbl` → `` `db`.`tbl` ``

    dialect ∈ {mysql, clickhouse, postgresql, oracle, sqlserver, hive}
    """
    if not ident:
        raise IdentifierError("ident 不能为空", value=ident)
    d = (dialect or "").lower()
    if d not in _DIALECT_QUOTE:
        raise IdentifierError(f"不支持的方言: {dialect}", value=ident)

    parts = ident.split(".")

    if d == "sqlserver":
        # SQLServer 用 [name]，仅 ] 需转义为 ]]
        return ".".join(f"[{p.replace(']', ']]')}]" for p in parts)

    quote_char, escape_pair = _DIALECT_QUOTE[d]
    return ".".join(
        f"{quote_char}{p.replace(quote_char, escape_pair)}{quote_char}" for p in parts
    )
