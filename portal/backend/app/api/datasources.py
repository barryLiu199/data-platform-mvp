from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import get_accessible_ids, check_resource_permission, require_permission
from app.models.datasource import DataSource
from app.models.user import SysUser

router = APIRouter(prefix="/datasources", tags=["数据源"])


# 支持的数据源类型元数据 — 前端从此处动态加载，新增类型在 db_adapters 注册后追加一行即可
DS_TYPE_META = [
    {"type": "mysql",      "label": "MySQL",       "default_port": 3306,  "color": "blue"},
    {"type": "sqlserver",  "label": "SQL Server",  "default_port": 1433,  "color": "purple"},
    {"type": "postgresql", "label": "PostgreSQL",  "default_port": 5432,  "color": "cyan"},
    {"type": "oracle",     "label": "Oracle",      "default_port": 1521,  "color": "red"},
    {"type": "clickhouse", "label": "ClickHouse",  "default_port": 8123,  "color": "orange"},
    {"type": "mongodb",    "label": "MongoDB",     "default_port": 27017, "color": "green"},
]


@router.get("/types")
def list_datasource_types():
    """返回支持的数据源类型列表（无需认证，前端表单初始化用）"""
    return DS_TYPE_META


class DataSourceCreate(BaseModel):
    name: str
    type: str  # mysql / postgresql / sqlserver / oracle / clickhouse / mongodb / redis / hive
    host: str
    port: int
    database_name: str
    username: Optional[str] = None
    password: Optional[str] = None
    description: Optional[str] = None


class DataSourceUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    description: Optional[str] = None


def _serialize(ds: DataSource) -> dict:
    return {
        "id": ds.id,
        "name": ds.name,
        "type": ds.type,
        "host": ds.host,
        "port": ds.port,
        "database_name": ds.database_name,
        "username": ds.username,
        "description": ds.description,
        "status": ds.status,
        "last_check_time": str(ds.last_check_time) if ds.last_check_time else None,
        "created_at": str(ds.created_at) if ds.created_at else None,
    }


@router.get("")
def list_datasources(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    query = db.query(DataSource)
    if keyword:
        query = query.filter(DataSource.name.contains(keyword))

    # 资源级 ACL 过滤
    accessible = get_accessible_ids(db, current_user, "datasource", "read")
    if accessible is not None:
        query = query.filter(DataSource.id.in_(accessible)) if accessible else query.filter(False)

    total = query.count()
    items = query.order_by(DataSource.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "items": [_serialize(ds) for ds in items]}


@router.post("")
def create_datasource(
    req: DataSourceCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("datasource:write")),
):
    ds = DataSource(**req.model_dump(), created_by=current_user.id)
    db.add(ds)
    db.flush()  # 获取 ds.id

    # 自动授予创建者 admin 权限
    from app.models.resource_access import SysResourceAccess
    db.add(SysResourceAccess(
        resource_type="datasource",
        resource_id=ds.id,
        subject_type="user",
        subject_id=current_user.id,
        permission="admin",
        granted_by=current_user.id,
    ))

    db.commit()
    db.refresh(ds)
    return _serialize(ds)


@router.get("/{ds_id}")
def get_datasource(
    ds_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    ds = db.query(DataSource).filter(DataSource.id == ds_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    if not check_resource_permission(db, current_user, "datasource", ds_id, "read"):
        raise HTTPException(status_code=404, detail="数据源不存在")
    return _serialize(ds)


@router.put("/{ds_id}")
def update_datasource(
    ds_id: int,
    req: DataSourceUpdate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("datasource:write")),
):
    ds = db.query(DataSource).filter(DataSource.id == ds_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    if not check_resource_permission(db, current_user, "datasource", ds_id, "write"):
        raise HTTPException(status_code=404, detail="数据源不存在")
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(ds, key, value)
    db.commit()
    db.refresh(ds)
    return _serialize(ds)


@router.delete("/{ds_id}")
def delete_datasource(
    ds_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(require_permission("datasource:write")),
):
    ds = db.query(DataSource).filter(DataSource.id == ds_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    if not check_resource_permission(db, current_user, "datasource", ds_id, "admin"):
        raise HTTPException(status_code=404, detail="数据源不存在")
    # 清理 ACL 记录
    from app.models.resource_access import SysResourceAccess
    db.query(SysResourceAccess).filter(
        SysResourceAccess.resource_type == "datasource",
        SysResourceAccess.resource_id == ds_id,
    ).delete()
    db.delete(ds)
    db.commit()
    return {"message": "删除成功"}


@router.post("/{ds_id}/test")
def test_connection(
    ds_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(get_current_user),
):
    ds = db.query(DataSource).filter(DataSource.id == ds_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="数据源不存在")
    if not check_resource_permission(db, current_user, "datasource", ds_id, "read"):
        raise HTTPException(status_code=404, detail="数据源不存在")

    from app.core.db_adapter import test_connection as adapter_test
    ok, msg = adapter_test(ds)
    ds.status = 1 if ok else 0
    db.commit()
    return {"message": msg, "status": ds.status}
