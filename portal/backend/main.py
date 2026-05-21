import sys
import os
import logging
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: run bootstrap (DDL + migrations + seed). Shutdown: cleanup."""
    from app.bootstrap import bootstrap
    bootstrap()
    yield


app = FastAPI(
    title="数据中台 MVP",
    description="金融行业离线数据中台统一门户 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Register routers ─────────────────────────────────────────────────────────
from app.api import (
    auth, datasources, sync_tasks, dashboard, ds_proxy,
    notifications, component, workflow, system, metadata, metadata_lineage,
    project, alert_rules, word_roots, admin, transfer,
)

for router_module in [
    auth, datasources, sync_tasks, dashboard, ds_proxy,
    notifications, component, workflow, system, metadata, metadata_lineage,
    project, alert_rules, word_roots, admin, transfer,
]:
    app.include_router(router_module.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "portal-backend"}
