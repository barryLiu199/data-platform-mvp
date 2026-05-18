from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_permission
from .config import _redact

router = APIRouter()

_VALID_CHANNEL_TYPES = {"email", "feishu_webhook", "dingtalk_webhook", "wecom_webhook"}


class NotifyChannelCreate(BaseModel):
    name: str
    type: str
    config: dict
    enabled: bool = True


class NotifyChannelUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    config: Optional[dict] = None
    enabled: Optional[bool] = None


@router.get("/notify-channels")
def list_notify_channels(
    db: Session = Depends(get_db),
    _=Depends(require_permission("system:config")),
):
    from app.models.sys_notify_channel import SysNotifyChannel
    channels = db.query(SysNotifyChannel).order_by(SysNotifyChannel.id.desc()).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "type": c.channel_type,
            "config": _redact(c.config) if c.config else None,
            "enabled": c.enabled,
            "created_at": str(c.created_at) if c.created_at else None,
            "updated_at": str(c.updated_at) if c.updated_at else None,
        }
        for c in channels
    ]


@router.post("/notify-channels", status_code=201)
def create_notify_channel(
    body: NotifyChannelCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("system:config")),
):
    from app.models.sys_notify_channel import SysNotifyChannel
    if body.type not in _VALID_CHANNEL_TYPES:
        raise HTTPException(400, f"无效的渠道类型: {body.type}")
    ch = SysNotifyChannel(
        name=body.name,
        channel_type=body.type,
        config=body.config,
        enabled=body.enabled,
        created_by=current_user.id,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return {"id": ch.id, "name": ch.name, "type": ch.channel_type}


@router.put("/notify-channels/{channel_id}")
def update_notify_channel(
    channel_id: int,
    body: NotifyChannelUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_permission("system:config")),
):
    from app.models.sys_notify_channel import SysNotifyChannel
    ch = db.query(SysNotifyChannel).filter(SysNotifyChannel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "渠道不存在")
    if body.name is not None:
        ch.name = body.name
    if body.type is not None:
        if body.type not in _VALID_CHANNEL_TYPES:
            raise HTTPException(400, f"无效的渠道类型: {body.type}")
        ch.channel_type = body.type
    if body.config is not None:
        ch.config = body.config
    if body.enabled is not None:
        ch.enabled = body.enabled
    db.commit()
    return {"ok": True}


@router.delete("/notify-channels/{channel_id}")
def delete_notify_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("system:config")),
):
    from app.models.sys_notify_channel import SysNotifyChannel
    ch = db.query(SysNotifyChannel).filter(SysNotifyChannel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "渠道不存在")
    db.delete(ch)
    db.commit()
    return {"ok": True}


@router.post("/notify-channels/{channel_id}/test")
async def test_notify_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_permission("system:config")),
):
    from app.models.sys_notify_channel import SysNotifyChannel
    from app.core.notifier import test_channel
    ch = db.query(SysNotifyChannel).filter(SysNotifyChannel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "渠道不存在")
    ok = await test_channel(ch.channel_type, ch.config or {})
    if not ok:
        raise HTTPException(502, "通知发送失败，请检查渠道配置")
    return {"ok": True, "channel_name": ch.name}
