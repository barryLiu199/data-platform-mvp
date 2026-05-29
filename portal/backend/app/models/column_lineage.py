from sqlalchemy import Column, BigInteger, String, DateTime, Text, Index, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class ColumnLineage(Base):
    """字段级血缘关系 — 由 column_lineage_service.refresh_column_lineage() 全量刷新

    与 TableLineage 平级、互不依赖。失败隔离：单 entity 解析失败写入 ColumnParseFailure，
    不影响其他 entity；本服务整体崩坏不影响表级血缘端点。
    """
    __tablename__ = "column_lineage"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_table = Column(String(256), nullable=False, comment="上游表名（lower）")
    source_column = Column(String(256), nullable=False, comment="上游字段名（lower）")
    target_table = Column(String(256), nullable=False, comment="下游表名（lower）")
    target_column = Column(String(256), nullable=False, comment="下游字段名（lower）")
    source_ds_id = Column(BigInteger, comment="上游数据源 ID")
    target_ds_id = Column(BigInteger, comment="下游数据源 ID")
    entity_type = Column(String(32), nullable=False, comment="sync_task / component / manual")
    entity_id = Column(BigInteger, comment="实体 ID（manual 时为 NULL）")
    entity_name = Column(String(255), comment="实体名称（冗余用于显示）")
    transform_type = Column(String(32), comment="identity / expression / aggregate / join")
    transform_expr = Column(Text, comment="转换表达式（仅 expression/aggregate 用）")
    parse_type = Column(String(32), comment="datax / sqlglot / regex / manual")
    parse_status = Column(String(16), default="ok", comment="ok / failed / partial")
    parse_error = Column(Text, comment="解析失败原因")
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(BigInteger, comment="manual 类型记录创建人")

    __table_args__ = (
        Index("idx_col_lineage_source", "source_table", "source_column"),
        Index("idx_col_lineage_target", "target_table", "target_column"),
        Index("idx_col_lineage_entity", "entity_type", "entity_id"),
    )


class ColumnParseFailure(Base):
    """字段血缘解析失败清单 — 同实体只保留最新一次失败"""
    __tablename__ = "column_parse_failure"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    entity_type = Column(String(32), nullable=False, comment="component")
    entity_id = Column(BigInteger, nullable=False)
    entity_name = Column(String(255))
    sql_snippet = Column(Text, comment="SQL 截断到 500 字符")
    error_msg = Column(Text, comment="sqlglot 报错")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uk_col_parse_fail_entity"),
    )
