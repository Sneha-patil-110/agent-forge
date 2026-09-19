from __future__ import annotations

import logging
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def create_db_engine(database_url: str | None = None) -> Engine | None:
    url = database_url or settings.DATABASE_URL

    if not url:
        return None

    try:
        engine = create_engine(url, pool_pre_ping=True, future=True)
        with engine.connect():
            pass
    except Exception:
        logger.warning("Could not connect to DATABASE_URL; database features disabled.", exc_info=True)
        return None

    return engine


def session_factory_for(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def make_session_scope(session_factory: sessionmaker[Session] | None):
    def _get_session() -> Iterator[Session]:
        if session_factory is None:
            raise RuntimeError("No database is configured (DATABASE_URL is unset or unreachable).")

        session = session_factory()

        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return _get_session