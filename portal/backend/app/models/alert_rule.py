from sqlalchemy import Column, BigInteger, String, Integer, Boolean, DateTime, JSON
from sqlalchemy.sql import func

from app.core.database import Base


class AlertRule(Base):
    """监控告警规则"""
    __tablename__ = "alert_rule"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    # 监控对象: all=所有工作流, workflow=指定工作流
    target_type = Column(String(32), nullable=False, default="all")
    target_id = Column(BigInteger, nullable=True)
    # 触发条件: failure / timeout / consecutive_failure
    trigger_type = Column(String(32), nullable=False)
    trigger_value = Column(Integer, nullable=True)  # 超时秒数 / 连续失败次数
    # 通知渠道: email / feishu_webhook
    notify_type = Column(String(32), nullable=False)
    notify_config = Column(JSON, nullable=False)  # {email:"x"} 或 {webhook_url:"x"}
    # 通知渠道 ID 列表
    notify_channel_ids = Column(JSON, nullable=True)
    # 开关
    enabled = Column(Boolean, default=True, nullable=False)
    created_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
