from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from datetime import datetime
from app.core.database import Base


class SysNotifyChannel(Base):
    __tablename__ = "sys_notify_channel"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="渠道名称")
    channel_type = Column(String(50), nullable=False, comment="渠道类型: email/webhook/dingtalk")
    config = Column(Text, comment="渠道配置JSON")
    enabled = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
