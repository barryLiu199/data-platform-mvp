"""数据库 schema 迁移：按需 ALTER TABLE / CREATE TABLE，幂等可重复执行。"""
from sqlalchemy import text
from app.core.database import engine


def run_all_migrations():
    _migrate_sync_task_columns()
    _migrate_component_columns()
    _migrate_workflow_run_columns()
    _migrate_workflow_project_id()
    _migrate_workflow_version_table()
    _migrate_alert_rule_table()
    _migrate_word_root_table()
    _migrate_component_sort_order()
    _migrate_folder_sort_order()
    _migrate_sys_user_columns()
    _migrate_sys_user_oauth_unique()
    _migrate_sys_notify_channel_table()
    _migrate_alert_rule_channel_ids()
    _migrate_workflow_params()
    _migrate_table_lineage()
    _migrate_lock_columns()
    _migrate_backfill_tables()
    _migrate_backfill_ds_columns()


def _migrate_backfill_tables():
    """Backfill 任务与实例表（幂等）"""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ('backfill_task','backfill_instance')"
        )).fetchall()
        existing = {r[0] for r in rows}
        if 'backfill_task' not in existing:
            conn.execute(text("""
                CREATE TABLE backfill_task (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    workflow_id BIGINT NOT NULL,
                    workflow_name VARCHAR(255),
                    date_from DATE NOT NULL,
                    date_to DATE NOT NULL,
                    parallel INT NOT NULL DEFAULT 1 COMMENT '最大并行实例数 1-20',
                    has_dep TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1=串行(有日依赖) 0=并行',
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    total_count INT NOT NULL DEFAULT 0,
                    success_count INT NOT NULL DEFAULT 0,
                    failed_count INT NOT NULL DEFAULT 0,
                    created_by BIGINT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    finished_at DATETIME NULL,
                    INDEX idx_backfill_workflow (workflow_id),
                    INDEX idx_backfill_created (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()
        if 'backfill_instance' not in existing:
            conn.execute(text("""
                CREATE TABLE backfill_instance (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    backfill_id BIGINT NOT NULL,
                    run_date DATE NOT NULL,
                    seq INT NOT NULL COMMENT '执行顺序，从 1 开始',
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    started_at DATETIME NULL,
                    finished_at DATETIME NULL,
                    error_msg TEXT NULL,
                    INDEX idx_backfill_id (backfill_id),
                    INDEX idx_backfill_status (backfill_id, status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()


def _migrate_table_lineage():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'table_lineage'"
        )).fetchall()
        if not rows:
            conn.execute(text("""
                CREATE TABLE table_lineage (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    source_table VARCHAR(256) NOT NULL COMMENT '上游表名',
                    target_table VARCHAR(256) NOT NULL COMMENT '下游表名',
                    source_ds_id BIGINT NULL COMMENT '上游数据源ID',
                    target_ds_id BIGINT NULL COMMENT '下游数据源ID',
                    entity_type VARCHAR(32) NOT NULL COMMENT 'sync_task/component',
                    entity_id BIGINT NOT NULL COMMENT '实体ID',
                    entity_name VARCHAR(255) NULL COMMENT '实体名称',
                    parse_type VARCHAR(32) NULL COMMENT 'datax/sql_ast/sql_regex',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_lineage_source (source_table),
                    INDEX idx_lineage_target (target_table),
                    INDEX idx_lineage_entity (entity_type, entity_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()


def _migrate_sync_task_columns():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sync_task'"
        )).fetchall()
        existing = {r[0] for r in rows}
        adds = [
            ("project_id",    "ALTER TABLE sync_task ADD COLUMN project_id BIGINT NULL COMMENT '所属项目'"),
            ("field_mapping", "ALTER TABLE sync_task ADD COLUMN field_mapping TEXT NULL COMMENT '字段映射JSON'"),
            ("where_clause",  "ALTER TABLE sync_task ADD COLUMN where_clause TEXT NULL COMMENT '源端WHERE过滤'"),
            ("split_pk",      "ALTER TABLE sync_task ADD COLUMN split_pk VARCHAR(128) NULL COMMENT 'DataX splitPk'"),
            ("write_mode",    "ALTER TABLE sync_task ADD COLUMN write_mode VARCHAR(32) DEFAULT 'insert' COMMENT '写入模式'"),
            ("pre_sql",       "ALTER TABLE sync_task ADD COLUMN pre_sql TEXT NULL COMMENT '导入前SQL JSON数组'"),
            ("post_sql",      "ALTER TABLE sync_task ADD COLUMN post_sql TEXT NULL COMMENT '导入后SQL JSON数组'"),
            ("channel",       "ALTER TABLE sync_task ADD COLUMN channel INT DEFAULT 3 COMMENT 'DataX并发通道数'"),
        ]
        for col, ddl in adds:
            if col not in existing:
                conn.execute(text(ddl))
                conn.commit()


def _migrate_component_columns():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'component'"
        )).fetchall()
        existing = {r[0] for r in rows}
        if 'folder_id' not in existing:
            conn.execute(text(
                "ALTER TABLE component ADD COLUMN folder_id BIGINT NULL COMMENT '所属文件夹'"
            ))
            conn.commit()


def _migrate_workflow_run_columns():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'workflow'"
        )).fetchall()
        existing = {r[0] for r in rows}
        adds = [
            ("priority",         "ALTER TABLE workflow ADD COLUMN priority INT NOT NULL DEFAULT 3 COMMENT '优先级 1=P1高 2=P2中 3=P3低'"),
            ("last_run_status",  "ALTER TABLE workflow ADD COLUMN last_run_status VARCHAR(50) NULL COMMENT '最近运行状态'"),
            ("last_run_time",    "ALTER TABLE workflow ADD COLUMN last_run_time DATETIME NULL COMMENT '最近运行时间'"),
            ("last_run_duration","ALTER TABLE workflow ADD COLUMN last_run_duration INT NULL COMMENT '最近运行耗时秒'"),
        ]
        for col, ddl in adds:
            if col not in existing:
                conn.execute(text(ddl))
                conn.commit()


def _migrate_workflow_project_id():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'workflow'"
        )).fetchall()
        existing = {r[0] for r in rows}
        if 'project_id' not in existing:
            conn.execute(text(
                "ALTER TABLE workflow ADD COLUMN project_id BIGINT NULL COMMENT '所属项目'"
            ))
            conn.commit()


def _migrate_workflow_version_table():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'workflow_version'"
        )).fetchall()
        if not rows:
            conn.execute(text("""
                CREATE TABLE workflow_version (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    workflow_id BIGINT NOT NULL,
                    version INT NOT NULL,
                    name VARCHAR(255),
                    description TEXT,
                    tags JSON,
                    dag_json JSON,
                    steps_json JSON,
                    cron_expression VARCHAR(100),
                    priority INT,
                    comment VARCHAR(500),
                    published_by BIGINT,
                    published_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_workflow_id (workflow_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()


def _migrate_alert_rule_table():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'alert_rule'"
        )).fetchall()
        if not rows:
            conn.execute(text("""
                CREATE TABLE alert_rule (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(128) NOT NULL,
                    target_type VARCHAR(32) NOT NULL DEFAULT 'all',
                    target_id BIGINT NULL,
                    trigger_type VARCHAR(32) NOT NULL,
                    trigger_value INT NULL,
                    notify_type VARCHAR(32) NOT NULL,
                    notify_config JSON NOT NULL,
                    notify_channel_ids JSON NULL COMMENT '通知渠道ID列表',
                    enabled TINYINT NOT NULL DEFAULT 1,
                    created_by BIGINT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()


def _migrate_word_root_table():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'word_root'"
        )).fetchall()
        if not rows:
            conn.execute(text("""
                CREATE TABLE word_root (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    en VARCHAR(64) NOT NULL COMMENT '英文词根',
                    cn VARCHAR(64) NOT NULL COMMENT '中文名',
                    category VARCHAR(32) NOT NULL DEFAULT 'business' COMMENT 'business/technical/metric',
                    description VARCHAR(255) NULL COMMENT '说明',
                    example VARCHAR(255) NULL COMMENT '示例用法',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_en (en)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()


def _migrate_component_sort_order():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'component'"
        )).fetchall()
        existing = {r[0] for r in rows}
        if 'sort_order' not in existing:
            conn.execute(text(
                "ALTER TABLE component ADD COLUMN sort_order INT NOT NULL DEFAULT 0 COMMENT '同文件夹内排序'"
            ))
            conn.commit()


def _migrate_folder_sort_order():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'component_folder'"
        )).fetchall()
        existing = {r[0] for r in rows}
        if 'sort_order' not in existing:
            conn.execute(text(
                "ALTER TABLE component_folder ADD COLUMN sort_order INT NOT NULL DEFAULT 0 COMMENT '同层级排序'"
            ))
            conn.commit()


def _migrate_sys_user_columns():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sys_user'"
        )).fetchall()
        existing = {r[0] for r in rows}
        adds = [
            ("avatar",         "ALTER TABLE sys_user ADD COLUMN avatar VARCHAR(512) NULL COMMENT '头像URL'"),
            ("dept_id",        "ALTER TABLE sys_user ADD COLUMN dept_id BIGINT NULL COMMENT '部门ID'"),
            ("last_login_at",  "ALTER TABLE sys_user ADD COLUMN last_login_at DATETIME NULL COMMENT '最近登录时间'"),
            ("oauth_provider", "ALTER TABLE sys_user ADD COLUMN oauth_provider VARCHAR(32) NULL COMMENT 'SSO提供商'"),
            ("oauth_openid",   "ALTER TABLE sys_user ADD COLUMN oauth_openid VARCHAR(128) NULL COMMENT 'SSO OpenID'"),
        ]
        for col, ddl in adds:
            if col not in existing:
                conn.execute(text(ddl))
                conn.commit()


def _migrate_sys_user_oauth_unique():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT INDEX_NAME FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sys_user' "
            "AND INDEX_NAME = 'uk_oauth'"
        )).fetchall()
        if not rows:
            conn.execute(text(
                "ALTER TABLE sys_user ADD UNIQUE KEY uk_oauth (oauth_provider, oauth_openid)"
            ))
            conn.commit()


def _migrate_sys_notify_channel_table():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sys_notify_channel'"
        )).fetchall()
        if not rows:
            conn.execute(text("""
                CREATE TABLE sys_notify_channel (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(128) NOT NULL COMMENT '渠道名称',
                    type VARCHAR(32) NOT NULL COMMENT 'email/feishu_webhook/dingtalk_webhook/wecom_webhook',
                    config JSON NOT NULL COMMENT '渠道配置JSON',
                    enabled TINYINT NOT NULL DEFAULT 1,
                    created_by BIGINT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()


def _migrate_alert_rule_channel_ids():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'alert_rule'"
        )).fetchall()
        existing = {r[0] for r in rows}
        if 'notify_channel_ids' not in existing:
            conn.execute(text(
                "ALTER TABLE alert_rule ADD COLUMN notify_channel_ids JSON NULL COMMENT '通知渠道ID列表'"
            ))
            conn.commit()


def _migrate_workflow_params():
    """workflow / workflow_version 添加 params_json 列"""
    with engine.connect() as conn:
        for table in ['workflow', 'workflow_version']:
            rows = conn.execute(text(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table}'"
            )).fetchall()
            existing = {r[0] for r in rows}
            if 'params_json' not in existing:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN params_json JSON NULL COMMENT '工作流全局参数'"
                ))
                conn.commit()


def _migrate_lock_columns():
    """给 component 和 sync_task 表加编辑锁字段"""
    with engine.connect() as conn:
        for table in ('component', 'sync_task'):
            rows = conn.execute(text(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tbl"
            ), {"tbl": table}).fetchall()
            existing = {r[0] for r in rows}
            if 'locked_by' not in existing:
                conn.execute(text(
                    f"ALTER TABLE `{table}` ADD COLUMN locked_by BIGINT NULL COMMENT '编辑锁持有者 user_id'"
                ))
                conn.commit()
            if 'locked_at' not in existing:
                conn.execute(text(
                    f"ALTER TABLE `{table}` ADD COLUMN locked_at DATETIME NULL COMMENT '抢锁时间'"
                ))
                conn.commit()


def _migrate_backfill_ds_columns():
    """backfill_task 加 ds_command_type/ds_command_id，backfill_instance 加 ds_instance_id"""
    with engine.connect() as conn:
        # backfill_task
        rows = conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'backfill_task'"
        )).fetchall()
        existing = {r[0] for r in rows}
        if 'ds_command_type' not in existing:
            conn.execute(text(
                "ALTER TABLE backfill_task ADD COLUMN ds_command_type VARCHAR(32) NULL "
                "COMMENT 'DS 执行类型，如 COMPLEMENT_DATA'"
            ))
            conn.commit()
        if 'ds_command_id' not in existing:
            conn.execute(text(
                "ALTER TABLE backfill_task ADD COLUMN ds_command_id BIGINT NULL "
                "COMMENT 'DS complement 命令 ID'"
            ))
            conn.commit()

        # backfill_instance
        rows = conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'backfill_instance'"
        )).fetchall()
        existing = {r[0] for r in rows}
        if 'ds_instance_id' not in existing:
            conn.execute(text(
                "ALTER TABLE backfill_instance ADD COLUMN ds_instance_id BIGINT NULL "
                "COMMENT 'DS process instance id'"
            ))
            conn.commit()
