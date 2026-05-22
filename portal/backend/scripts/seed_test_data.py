#!/usr/bin/env python3
"""seed_test_data.py — 幂等种子脚本，直接 INSERT 到 Portal DB（不走 DS）

用法:
  docker exec -it dmp-portal-api python /app/scripts/seed_test_data.py

包含:
  1x DataSource (复用已有 or 新建 demo_portal_mysql)
  1x ComponentFolder "Demo"
  4x Component: sql / python / shell / procedure
  1x Workflow (draft, DAG: sql → python → shell)
  3x BackfillTask + 15 BackfillInstance
"""
import sys
import os
from datetime import date, datetime, timedelta

# 确保 app 可 import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import SessionLocal, engine
from app.models.datasource import DataSource
from app.models.component_folder import ComponentFolder
from app.models.component import Component
from app.models.workflow import Workflow
from app.models.backfill import BackfillTask, BackfillInstance

ADMIN_USER_ID = 1
PREFIX = "demo_"


def cleanup(db):
    """删除旧的 demo 数据（按 name LIKE 'demo_%' 和固定前缀）"""
    # BackfillInstance → BackfillTask (要先删子表)
    demo_bt_ids = [
        r[0] for r in db.query(BackfillTask.id).filter(BackfillTask.workflow_name.like(f"{PREFIX}%")).all()
    ]
    if demo_bt_ids:
        db.query(BackfillInstance).filter(BackfillInstance.backfill_id.in_(demo_bt_ids)).delete(synchronize_session=False)
        db.query(BackfillTask).filter(BackfillTask.id.in_(demo_bt_ids)).delete(synchronize_session=False)

    # Workflow
    db.query(Workflow).filter(Workflow.name.like(f"{PREFIX}%")).delete(synchronize_session=False)
    # Component
    db.query(Component).filter(Component.name.like(f"{PREFIX}%")).delete(synchronize_session=False)
    # ComponentFolder
    db.query(ComponentFolder).filter(ComponentFolder.name == "Demo").delete(synchronize_session=False)
    # DataSource (只删我们自己建的)
    db.query(DataSource).filter(DataSource.name == "demo_portal_mysql").delete(synchronize_session=False)
    db.commit()
    print("[cleanup] 旧 demo 数据已清理")


def seed_datasource(db) -> int:
    """复用已有数据源 or 新建。返回 id"""
    existing = db.query(DataSource).filter(DataSource.type == "mysql").first()
    if existing:
        print(f"[datasource] 复用已有: id={existing.id} name={existing.name}")
        return existing.id
    ds = DataSource(
        name="demo_portal_mysql",
        type="mysql",
        host="dmp-mysql",
        port=3306,
        database_name="data_platform",
        username="root",
        password="root123",
        description="Demo 测试数据源 - Portal 自身库",
        status=1,
        created_by=ADMIN_USER_ID,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    print(f"[datasource] 新建: id={ds.id}")
    return ds.id


def seed_folder(db) -> int:
    """创建 Demo 组件目录，返回 id"""
    folder = ComponentFolder(
        name="Demo",
        type="sql",
        parent_id=None,
        depth=0,
        created_by=ADMIN_USER_ID,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    print(f"[folder] Demo id={folder.id}")
    return folder.id


def seed_components(db, ds_id: int, folder_id: int) -> dict:
    """创建 4 个组件，返回 {type: component_id}"""
    components = [
        Component(
            name="demo_统计用户数",
            type="sql",
            description="演示 SQL 组件：统计 sys_user 行数",
            config_json={
                "datasource_id": ds_id,
                "sql": "SET @bizdate = '${run_date}';\nSELECT @bizdate AS biz_date, COUNT(*) AS user_count FROM sys_user;",
                "timeout": 30,
            },
            folder_id=folder_id,
            status="tested",
            created_by=ADMIN_USER_ID,
        ),
        Component(
            name="demo_Python脚本",
            type="python",
            description="演示 Python 组件：打印业务日期 + sleep",
            config_json={
                "script": "import time\nprint(f'业务日期: ${run_date}')\ntime.sleep(2)\nprint('完成')",
                "timeout": 30,
            },
            folder_id=folder_id,
            status="tested",
            created_by=ADMIN_USER_ID,
        ),
        Component(
            name="demo_Shell脚本",
            type="shell",
            description="演示 Shell 组件：echo + date",
            config_json={
                "script": "echo \"业务日期=${run_date}\"\ndate\necho \"done\"",
                "timeout": 30,
            },
            folder_id=folder_id,
            status="tested",
            created_by=ADMIN_USER_ID,
        ),
        Component(
            name="demo_存储过程",
            type="procedure",
            description="演示存储过程组件（需手动建 proc 才能运行）",
            config_json={
                "datasource_id": ds_id,
                "procedure_name": "sp_demo_report",
                "params": ["${run_date}"],
                "timeout": 60,
            },
            folder_id=folder_id,
            status="draft",
            created_by=ADMIN_USER_ID,
        ),
    ]
    db.add_all(components)
    db.commit()
    for c in components:
        db.refresh(c)
    result = {c.type: c.id for c in components}
    print(f"[components] 创建 {len(components)} 个: {result}")
    return result


def seed_workflow(db, comp_ids: dict) -> int:
    """创建 DAG 工作流 (sql → python → shell)，返回 id"""
    sql_id = comp_ids["sql"]
    py_id = comp_ids["python"]
    sh_id = comp_ids["shell"]

    dag_json = {
        "nodes": [
            {"id": "n1", "component_id": sql_id, "name": "demo_统计用户数", "position": {"x": 100, "y": 200}},
            {"id": "n2", "component_id": py_id, "name": "demo_Python脚本", "position": {"x": 350, "y": 200}},
            {"id": "n3", "component_id": sh_id, "name": "demo_Shell脚本", "position": {"x": 600, "y": 200}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},
        ],
    }
    steps_json = [
        {"component_id": sql_id, "name": "demo_统计用户数"},
        {"component_id": py_id, "name": "demo_Python脚本"},
        {"component_id": sh_id, "name": "demo_Shell脚本"},
    ]

    wf = Workflow(
        name="demo_日报数据Pipeline",
        description="演示工作流：SQL统计 → Python处理 → Shell通知",
        tags=["demo", "日报"],
        project_id=None,  # 未分组
        dag_json=dag_json,
        steps_json=steps_json,
        status="draft",
        priority=2,
        params_json=[
            {"prop": "run_date", "direct": "IN", "type": "VARCHAR", "value": "2026-05-01"},
        ],
        created_by=ADMIN_USER_ID,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    print(f"[workflow] demo_日报数据Pipeline id={wf.id}")
    return wf.id


def seed_backfill(db, wf_id: int):
    """创建 3 个补数任务 + 实例：全成功 / 部分失败 / 运行中"""
    today = date.today()

    # --- Task 1: 全部成功 (5天) ---
    t1 = BackfillTask(
        workflow_id=wf_id,
        workflow_name="demo_日报数据Pipeline",
        date_from=today - timedelta(days=5),
        date_to=today - timedelta(days=1),
        parallel=3,
        has_dep=0,
        status="succeeded",
        total_count=5,
        success_count=5,
        failed_count=0,
        created_by=ADMIN_USER_ID,
        finished_at=datetime.now() - timedelta(hours=2),
    )
    db.add(t1)
    db.commit()
    db.refresh(t1)
    for seq in range(1, 6):
        d = today - timedelta(days=6 - seq)
        db.add(BackfillInstance(
            backfill_id=t1.id,
            run_date=d,
            seq=seq,
            status="success",
            started_at=datetime.now() - timedelta(hours=3, minutes=seq * 5),
            finished_at=datetime.now() - timedelta(hours=2, minutes=seq * 5),
        ))

    # --- Task 2: 部分失败 (5天，3成功2失败) ---
    t2 = BackfillTask(
        workflow_id=wf_id,
        workflow_name="demo_日报数据Pipeline",
        date_from=today - timedelta(days=10),
        date_to=today - timedelta(days=6),
        parallel=2,
        has_dep=1,
        status="failed",
        total_count=5,
        success_count=3,
        failed_count=2,
        created_by=ADMIN_USER_ID,
        finished_at=datetime.now() - timedelta(hours=5),
    )
    db.add(t2)
    db.commit()
    db.refresh(t2)
    for seq in range(1, 6):
        d = today - timedelta(days=11 - seq)
        status = "success" if seq <= 3 else "failed"
        error_msg = "ERROR 2013 (HY000): Lost connection to MySQL server during query" if status == "failed" else None
        db.add(BackfillInstance(
            backfill_id=t2.id,
            run_date=d,
            seq=seq,
            status=status,
            started_at=datetime.now() - timedelta(hours=6, minutes=seq * 4),
            finished_at=datetime.now() - timedelta(hours=5, minutes=seq * 4),
            error_msg=error_msg,
        ))

    # --- Task 3: 运行中 (5天，2成功1运行中2待执行) ---
    t3 = BackfillTask(
        workflow_id=wf_id,
        workflow_name="demo_日报数据Pipeline",
        date_from=today - timedelta(days=4),
        date_to=today,
        parallel=1,
        has_dep=1,
        status="running",
        total_count=5,
        success_count=2,
        failed_count=0,
        created_by=ADMIN_USER_ID,
    )
    db.add(t3)
    db.commit()
    db.refresh(t3)
    statuses = ["success", "success", "running", "pending", "pending"]
    for seq, st in enumerate(statuses, 1):
        d = today - timedelta(days=5 - seq)
        started = datetime.now() - timedelta(minutes=30 * (5 - seq)) if st != "pending" else None
        finished = started + timedelta(minutes=10) if st == "success" and started else None
        db.add(BackfillInstance(
            backfill_id=t3.id,
            run_date=d,
            seq=seq,
            status=st,
            started_at=started,
            finished_at=finished,
        ))

    db.commit()
    print(f"[backfill] 3 tasks, 15 instances (全成功/部分失败/运行中)")


def main():
    print("=" * 60)
    print("seed_test_data.py — 幂等种子脚本")
    print("=" * 60)

    db = SessionLocal()
    try:
        cleanup(db)
        ds_id = seed_datasource(db)
        folder_id = seed_folder(db)
        comp_ids = seed_components(db, ds_id, folder_id)
        wf_id = seed_workflow(db, comp_ids)
        seed_backfill(db, wf_id)
        print("\n✓ 种子数据写入完成！")
        print("  前端查看：工作流开发 → demo_日报数据Pipeline")
        print("  组件开发 → Demo 目录下 4 个组件")
        print("  运行实例 → 补数任务可在列表看到")
    finally:
        db.close()


if __name__ == "__main__":
    main()
