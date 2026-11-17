from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    engine = create_engine(
        get_settings().db_url, connect_args={"check_same_thread": False, "timeout": 30}
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")  # API reads while the worker writes
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


def init_db() -> None:
    from app.db import models  # noqa: F401  (register tables)

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
