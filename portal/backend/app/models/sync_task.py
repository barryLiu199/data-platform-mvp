from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class SyncTask(Base):
    __tablename__ = "sync_task"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    project_id = Column(BigInteger, comment="所属项目 — NULL 时归属默认未分组项目")
    source_id = Column(BigInteger, nullable=False)
    target_id = Column(BigInteger, nullable=False)
    source_table = Column(String(128), nullable=False)
    target_table = Column(String(128), nullable=False)
    sync_type = Column(String(32), default="full")
    increment_column = Column(String(128))
    field_mapping = Column(Text, comment="字段映射 JSON 数组 [{kind,src,dst,type},...]")
    # ---- DataWorks 风格高级参数 ----
    where_clause = Column(Text, comment="源端 WHERE 过滤条件，支持 ${bizdate} 等变量")
    split_pk = Column(String(128), comment="DataX splitPk 切分键，提升并发")
    write_mode = Column(String(32), default="insert", comment="insert / replace / update")
    channel = Column(Integer, default=3, comment="DataX 并发通道数，1-32")
    pre_sql = Column(Text, comment="导入前 SQL 列表 JSON 数组（目标库执行）")
    post_sql = Column(Text, comment="导入后 SQL 列表 JSON 数组（目标库执行）")
    ds_workflow_id = Column(BigInteger)
    status = Column(String(32), default="draft")
    last_run_time = Column(DateTime)
    last_run_status = Column(String(32))
    created_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    locked_by = Column(BigInteger, comment="编辑锁持有者 user_id")
    locked_at = Column(DateTime, comment="抢锁时间")
