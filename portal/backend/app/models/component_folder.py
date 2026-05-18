from sqlalchemy import Column, BigInteger, String, Integer, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class ComponentFolder(Base):
    """组件文件夹 — 支持三级嵌套目录树"""

    __tablename__ = "component_folder"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    type = Column(String(50), nullable=False)  # sql / python / shell / datax
    parent_id = Column(BigInteger, comment="父文件夹 id, NULL 为根")
    depth = Column(Integer, default=0, comment="层级: 0=一级, 1=二级, 2=三级")
    created_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    sort_order = Column(Integer, default=0, comment="排序序号")
