from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import backend.db.models
from backend.core.config import settings
from backend.db.base import create_db_engine, session_factory_for

_TABLES = (
    "agent_invocations",
    "workflow_events",
    "knowledge_entries",
    "generated_projects",
    "projects",
    "file_versions",
    "documentation_files",
    "runs",
    "users",
)


@pytest.fixture(scope="session")
def test_db_engine() -> Engine:
    engine = create_db_engine(settings.TEST_DATABASE_URL)

    if engine is None:
        pytest.skip("TEST_DATABASE_URL is not configured or unreachable.")

    yield engine

    engine.dispose()


@pytest.fixture
def db_session_factory(test_db_engine: Engine) -> sessionmaker[Session]:
    yield session_factory_for(test_db_engine)

    with test_db_engine.connect() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
        connection.commit()


@pytest.fixture
def db_session(db_session_factory: sessionmaker[Session]):
    session = db_session_factory()

    yield session

    session.close()