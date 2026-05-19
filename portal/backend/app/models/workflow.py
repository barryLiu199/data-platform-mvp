from sqlalchemy import Column, BigInteger, String, Integer, Text, DateTime, JSON
from sqlalchemy.sql import func

from app.core.database import Base


class Workflow(Base):
    """DAG 工作流 — 组合多个 Component 形成可调度的有向无环图"""
    __tablename__ = "workflow"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    tags = Column(JSON, nullable=True)  # 标签列表，如 ["ODS同步", "日报"]
    project_id = Column(BigInteger, nullable=True, comment="所属项目")
    # 旧版线性步骤（兼容，新版优先使用 dag_json）
    steps_json = Column(JSON, nullable=False, default=list)
    # DAG 结构: {nodes: [{id, component_id, name, position:{x,y}, skip}], edges: [{id, source, target}]}
    dag_json = Column(JSON, nullable=True)
    # 调度 (CRON 表达式,可选)
    cron_expression = Column(String(100))
    # 调度状态: ONLINE / OFFLINE (DS 调度开关,与 status 是两回事)
    schedule_status = Column(String(50), default="OFFLINE", nullable=False)
    # 工作流生命周期: draft -> tested -> online -> offline
    status = Column(String(50), default="draft", nullable=False)
    version = Column(Integer, default=1, nullable=False)
    # 优先级: 1=P1高, 2=P2中, 3=P3低
    priority = Column(Integer, default=3, nullable=False)
    # 缓存最近运行信息（由 sync-last-run 端点更新）
    last_run_status = Column(String(50))
    last_run_time = Column(DateTime)
    last_run_duration = Column(Integer)
    # 发布后映射到 DS process-definition code (Phase 5/6 填入)
    ds_process_code = Column(BigInteger)
    # 调度 schedule id (Phase 5/6 填入)
    ds_schedule_id = Column(BigInteger)
    created_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class WorkflowVersion(Base):
    """工作流版本快照 — 每次发布时自动创建"""
    __tablename__ = "workflow_version"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id = Column(BigInteger, nullable=False, index=True)
    version = Column(Integer, nullable=False)
    name = Column(String(255))
    description = Column(Text)
    tags = Column(JSON)
    dag_json = Column(JSON)
    steps_json = Column(JSON)
    cron_expression = Column(String(100))
    priority = Column(Integer)
    comment = Column(String(500))
    published_by = Column(BigInteger)
    published_at = Column(DateTime, server_default=func.now())
