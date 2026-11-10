"""Database engine, session and base class."""
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


def make_engine(url: str = DATABASE_URL) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine_options = {"poolclass": StaticPool} if url.endswith(":memory:") or url == "sqlite://" else {}
    new_engine = create_engine(url, connect_args=connect_args, **engine_options)

    if url.startswith("sqlite"):
        # SQLite ignores foreign keys unless we switch them on.
        @event.listens_for(new_engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return new_engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(bind: Engine | None = None) -> None:
    """Create all tables. Alembic migrations come later."""
    from app.db import models  # noqa: F401  (registers the tables)

    Base.metadata.create_all(bind or engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
