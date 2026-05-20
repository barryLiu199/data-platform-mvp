from sqlalchemy import Column, BigInteger, String, DateTime, Index
from sqlalchemy.sql import func

from app.core.database import Base


class TableLineage(Base):
    """表级血缘关系 — 由 lineage_service.refresh_lineage() 全量刷新"""
    __tablename__ = "table_lineage"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_table = Column(String(256), nullable=False, comment="上游表名")
    target_table = Column(String(256), nullable=False, comment="下游表名")
    source_ds_id = Column(BigInteger, comment="上游数据源 ID")
    target_ds_id = Column(BigInteger, comment="下游数据源 ID")
    entity_type = Column(String(32), nullable=False, comment="sync_task / component")
    entity_id = Column(BigInteger, nullable=False, comment="实体 ID")
    entity_name = Column(String(255), comment="实体名称（冗余）")
    parse_type = Column(String(32), comment="datax / sql_ast / sql_regex")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_lineage_source", "source_table"),
        Index("idx_lineage_target", "target_table"),
        Index("idx_lineage_entity", "entity_type", "entity_id"),
    )
