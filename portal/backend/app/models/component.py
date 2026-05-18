from sqlalchemy import Column, BigInteger, String, Integer, Text, DateTime, JSON
from sqlalchemy.sql import func

from app.core.database import Base


class Component(Base):
    """统一组件模型 — sql / python / shell / datax"""
    __tablename__ = "component"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)  # sql / python / shell / datax
    description = Column(Text)
    # 配置 JSON,按 type 不同含义不同:
    #   sql:    { datasource_id, sql, timeout }
    #   python: { script, timeout }
    #   shell:  { script, timeout }
    #   datax:  { reader, writer, source_id, target_id, ... }
    config_json = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, default=1, nullable=False)
    # 状态机: draft -> tested -> online -> offline
    status = Column(String(50), default="draft", nullable=False)
    # 发布后映射到 DS Task code (Phase 5+ 填入)
    ds_task_code = Column(BigInteger)
    folder_id = Column(BigInteger, comment="所属文件夹 id")
    previous_status = Column(String(50), comment="暂停前的状态")
    created_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    sort_order = Column(Integer, default=0, comment="排序序号")
