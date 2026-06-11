"""Tests for app/core/validators.py — 白名单 + 方言引号"""
import pytest

from app.core.validators import (
    IdentifierError,
    quote_identifier,
    validate_sql_identifier,
)


# ─── validate_sql_identifier ─────────────────────────────────────────────

class TestValidateSqlIdentifier:
    @pytest.mark.parametrize("legal", [
        "a",
        "A",
        "_",
        "_x",
        "a_b",
        "A1",
        "abc123",
        "user_name",
        "schema.table",
        "public.users",
        "DW_USER.id_v2",
        "_schema._table",
        "a" * 256,  # 边界长度
    ])
    def test_legal(self, legal):
        assert validate_sql_identifier(legal) == legal

    @pytest.mark.parametrize("illegal", [
        "",
        " ",
        "1foo",          # 数字开头
        "1",
        "a-b",           # 短横线
        "a;b",           # 分号
        "a b",           # 空格
        "a\tb",          # tab
        "a\nb",          # 换行
        'a"b',           # 双引号
        "a'b",           # 单引号
        "a`b",           # 反引号
        "a.b.c",         # 多级点号
        "a..b",          # 连续点号
        ".a",            # 起始点号
        "a.",            # 结尾点号
        ".",
        "..",
        "a/b",
        "a\\b",
        "a*b",
        "a(b",
        "--comment",
        "/* x */",
        '"; DROP TABLE x',
        "t WHERE 1=1",
        "x] UNION SELECT",
        "evil`",
        "a%b",
        "a + b",
        "你好",          # 非 ASCII
        "user🚀",        # emoji
        "a" * 257,       # 超长
    ])
    def test_illegal_raises(self, illegal):
        with pytest.raises(IdentifierError):
            validate_sql_identifier(illegal)

    def test_none_raises(self):
        with pytest.raises(IdentifierError):
            validate_sql_identifier(None)  # type: ignore[arg-type]

    def test_non_str_raises(self):
        with pytest.raises(IdentifierError):
            validate_sql_identifier(123)  # type: ignore[arg-type]

    def test_field_in_error(self):
        with pytest.raises(IdentifierError) as ei:
            validate_sql_identifier("a;b", field="table_name")
        assert ei.value.field == "table_name"
        assert "table_name" in str(ei.value)


# ─── quote_identifier ────────────────────────────────────────────────────

class TestQuoteIdentifier:
    def test_mysql_basic(self):
        assert quote_identifier("mysql", "users") == "`users`"

    def test_mysql_schema_table(self):
        assert quote_identifier("mysql", "db.users") == "`db`.`users`"

    def test_clickhouse_basic(self):
        assert quote_identifier("clickhouse", "events") == "`events`"

    def test_postgresql_basic(self):
        assert quote_identifier("postgresql", "users") == '"users"'

    def test_postgresql_schema(self):
        assert quote_identifier("postgresql", "public.users") == '"public"."users"'

    def test_oracle_basic(self):
        assert quote_identifier("oracle", "T_USER") == '"T_USER"'

    def test_sqlserver_basic(self):
        assert quote_identifier("sqlserver", "users") == "[users]"

    def test_sqlserver_schema(self):
        assert quote_identifier("sqlserver", "dbo.users") == "[dbo].[users]"

    def test_hive_basic(self):
        assert quote_identifier("hive", "ods_user") == "`ods_user`"

    def test_dialect_case_insensitive(self):
        assert quote_identifier("MySQL", "x") == "`x`"
        assert quote_identifier("PostgreSQL", "x") == '"x"'

    # 引号字符转义 — 双重防御核心
    def test_mysql_escapes_backtick(self):
        # 输入中含反引号（理论上 validate 已挡住，但 quote 也要兜底）
        assert quote_identifier("mysql", "a`b") == "`a``b`"

    def test_postgresql_escapes_double_quote(self):
        assert quote_identifier("postgresql", 'a"b') == '"a""b"'

    def test_sqlserver_escapes_close_bracket(self):
        assert quote_identifier("sqlserver", "a]b") == "[a]]b]"

    def test_unsupported_dialect(self):
        with pytest.raises(IdentifierError):
            quote_identifier("mongodb", "x")

    def test_empty(self):
        with pytest.raises(IdentifierError):
            quote_identifier("mysql", "")
