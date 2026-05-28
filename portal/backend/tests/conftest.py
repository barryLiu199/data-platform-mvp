"""pytest fixtures: SQLite in-memory DB + dependency overrides"""
import os
import pytest
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from sqlalchemy import create_engine, event, BigInteger, Integer
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_test_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

# Patch the module-level engine before any app code imports it
import app.core.database as _db_module
_db_module.engine = _test_engine
_db_module.SessionLocal = _TestSession

from app.core.database import Base

# 导入所有模型，确保它们注册到 Base.metadata
import app.models.component  # noqa: F401
import app.models.component_folder  # noqa: F401
import app.models.datasource  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.project  # noqa: F401
import app.models.user  # noqa: F401
import app.models.backfill  # noqa: F401
import app.models.quality  # noqa: F401
try:
    import app.models.role  # noqa: F401
except ImportError:
    pass

# SQLite 不支持 BigInteger autoincrement，将所有 BigInteger PK 改为 Integer
# 这样 SQLite 的 ROWID 自动递增机制才能生效
for table in Base.metadata.tables.values():
    for col in table.columns:
        if isinstance(col.type, BigInteger) and col.primary_key:
            col.type = Integer()

Base.metadata.create_all(bind=_test_engine)


@pytest.fixture
def clean_tables():
    """确保表存在 + 测试后清空数据，保证测试隔离"""
    Base.metadata.create_all(bind=_test_engine)
    yield
    session = _TestSession()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
    finally:
        session.close()


@pytest.fixture
def db_session():
    session = _TestSession()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def client(db_session, clean_tables):
    """轻量 TestClient — 只挂 transfer router，不导入 main.py"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.transfer import router
    from app.core.database import get_db
    from app.core.security import get_current_user

    app = FastAPI()
    app.include_router(router, prefix="/api")

    fake_user = MagicMock()
    fake_user.id = 1
    fake_user.username = "testadmin"
    fake_user.role = "admin"

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: fake_user

    yield TestClient(app)
    app.dependency_overrides.clear()
