from __future__ import annotations

import os

import pytest
from sqlalchemy import text


os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://knowledge:knowledge@127.0.0.1:5432/knowledge_test?gssencmode=disable"
)
os.environ.setdefault("WAREHOUSE_GATEWAY_MODE", "mock")
os.environ.setdefault("WAREHOUSE_MOCK_ROOT", "/tmp/knowledge_test_runtime/mock_warehouse")
os.environ.setdefault("VECTOR_STORE_MODE", "db")
os.environ.setdefault("MODEL_PROVIDER_MODE", "mock")


def pytest_sessionstart(session: pytest.Session) -> None:
    import knowledge.models  # noqa: F401
    from knowledge.db.base import Base
    from knowledge.db.migrations import stamp_head
    from knowledge.db.schema import ensure_runtime_schema
    from knowledge.db.session import engine

    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)
    # Build the schema directly from the models for speed, then mark it at head so
    # the app lifespan's upgrade_to_head() is a no-op during tests.
    stamp_head()
