"""数据质量模型 — 规则模板、规则实例、检查结果"""
from sqlalchemy import (
    Column, BigInteger, String, Integer, Boolean, DateTime, Date, Float, Text, JSON,
    UniqueConstraint, Index,
)
from sqlalchemy.sql import func
from app.core.database import Base


class QualityRuleTemplate(Base):
    """内置规则模板（种子数据，用户不可增删）"""
    __tablename__ = "quality_rule_template"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False)
    name = Column(String(128), nullable=False)
    category = Column(String(32), nullable=False)
    level = Column(String(32), nullable=False)
    description = Column(Text)
    config_schema = Column(JSON, nullable=False)
    sql_template = Column(Text)
    display_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class QualityRule(Base):
    """用户创建的质量规则实例"""
    __tablename__ = "quality_rule"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    template_code = Column(String(64), nullable=False, index=True)
    datasource_id = Column(BigInteger, nullable=True)
    table_name = Column(String(256), nullable=True)
    column_name = Column(String(256), nullable=True)

    config = Column(JSON, nullable=False)

    severity = Column(String(16), nullable=False, default="warning")
    trigger_type = Column(String(32), nullable=False, default="manual")
    trigger_workflow_id = Column(BigInteger, nullable=True, index=True)

    notify_enabled = Column(Boolean, default=False, nullable=False)
    notify_channel_ids = Column(JSON, nullable=True)

    enabled = Column(Boolean, default=True, nullable=False)
    last_check_time = Column(DateTime, nullable=True)
    last_check_status = Column(String(16), nullable=True)

    created_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_qr_ds_table", "datasource_id", "table_name"),
    )


class QualityCheckResult(Base):
    """每次质量检查的结果"""
    __tablename__ = "quality_check_result"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rule_id = Column(BigInteger, nullable=False)
    check_date = Column(Date, nullable=False)
    status = Column(String(16), nullable=False)

    actual_value = Column(Float, nullable=True)
    expected_value = Column(Float, nullable=True)
    detail = Column(JSON, nullable=True)
    executed_sql = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    triggered_by = Column(String(32), nullable=False, default="manual")

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("rule_id", "check_date", name="uk_rule_date"),
        Index("idx_qcr_rule_date", "rule_id", "check_date"),
        Index("idx_qcr_date", "check_date"),
    )
