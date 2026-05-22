"""Backfill (补数据/归历史) 数据模型

- BackfillTask: 一次补数据任务，对应"工作流 + 日期范围 + 并行策略"
- BackfillInstance: 任务展开成的每一天的运行实例
"""
from sqlalchemy import Column, BigInteger, String, Integer, Date, DateTime, Text, Index
from sqlalchemy.sql import func

from app.core.database import Base


class BackfillTask(Base):
    __tablename__ = "backfill_task"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id = Column(BigInteger, nullable=False)
    workflow_name = Column(String(255))
    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=False)
    parallel = Column(Integer, default=1, nullable=False, comment="最大并行实例数 1-20")
    has_dep = Column(Integer, default=0, nullable=False, comment="1=串行(有日依赖) 0=并行")
    # pending / running / succeeded / failed / stopping / stopped
    status = Column(String(32), default="pending", nullable=False)
    total_count = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)
    created_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)


class BackfillInstance(Base):
    __tablename__ = "backfill_instance"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    backfill_id = Column(BigInteger, nullable=False, index=True)
    run_date = Column(Date, nullable=False)
    seq = Column(Integer, nullable=False, comment="执行顺序，从 1 开始")
    # pending / running / success / failed / skipped
    status = Column(String(32), default="pending", nullable=False)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    error_msg = Column(Text)

    __table_args__ = (
        Index("idx_backfill_status", "backfill_id", "status"),
    )
