from __future__ import annotations

from sqlalchemy import Engine, inspect, text


TASK_COLUMNS: dict[str, str] = {
    "claimed_by": "VARCHAR(128)",
    "claimed_at": "DATETIME",
    "heartbeat_at": "DATETIME",
    "attempt": "INTEGER",
    "last_stage": "TEXT",
}

TASK_ITEM_COLUMNS: dict[str, str] = {
    "stage": "VARCHAR(64)",
    "duration_ms": "INTEGER",
    "error_type": "VARCHAR(128)",
}

SOURCE_BINDING_COLUMNS: dict[str, str] = {
    "credential_id": "INTEGER",
}

RETRIEVAL_LOG_COLUMNS: dict[str, str] = {
    "agent_run_id": "VARCHAR(64)",
}

RUNTIME_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("import_tasks", "ix_import_tasks_status_created_at", "status, created_at"),
    ("import_tasks", "ix_import_tasks_owner_status_created_at", "owner_wallet_address, status, created_at"),
)


def ensure_runtime_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    with engine.begin() as connection:
        _ensure_columns(connection, inspector, "import_tasks", TASK_COLUMNS)
        _ensure_columns(connection, inspector, "import_task_items", TASK_ITEM_COLUMNS)
        _ensure_columns(connection, inspector, "source_bindings", SOURCE_BINDING_COLUMNS)
        _ensure_columns(connection, inspector, "retrieval_logs", RETRIEVAL_LOG_COLUMNS)
        _ensure_import_task_column_types(connection, inspector)
        inspector = inspect(connection)
        _ensure_indexes(connection, inspector)


def _ensure_columns(connection, inspector, table_name: str, columns: dict[str, str]) -> None:
    if not inspector.has_table(table_name):
        return
    existing = {column["name"] for column in inspector.get_columns(table_name)}
    for column_name, column_type in columns.items():
        if column_name in existing:
            continue
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


def _ensure_import_task_column_types(connection, inspector) -> None:
    if not inspector.has_table("import_tasks"):
        return
    columns = {column["name"]: column["type"] for column in inspector.get_columns("import_tasks")}
    last_stage_type = columns.get("last_stage")
    if last_stage_type is not None and getattr(last_stage_type, "length", None) is not None:
        connection.execute(text("ALTER TABLE import_tasks ALTER COLUMN last_stage TYPE TEXT"))


def _ensure_indexes(connection, inspector) -> None:
    existing = {index["name"] for _, index in _iter_indexes(inspector)}
    for table_name, index_name, columns_sql in RUNTIME_INDEXES:
        if index_name in existing:
            continue
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns_sql})"))


def _iter_indexes(inspector):
    for table_name in ("import_tasks", "import_task_items"):
        if not inspector.has_table(table_name):
            continue
        for index in inspector.get_indexes(table_name):
            yield table_name, index
