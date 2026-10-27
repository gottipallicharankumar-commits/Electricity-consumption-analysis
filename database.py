"""Database engine and schema helpers; SQLAlchemy binds all query parameters."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine

from modules.models import metadata


def create_database_engine(database_url: str, *, echo: bool = False) -> Engine:
    options: dict[str, object] = {"future": True, "pool_pre_ping": True, "echo": echo}
    if database_url.startswith("sqlite:"):
        options["connect_args"] = {"check_same_thread": False}
    engine = create_engine(database_url, **options)
    if database_url.startswith("sqlite:"):
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def initialize_schema(engine: Engine) -> None:
    """Create missing tables only; never drops or overwrites existing records."""
    metadata.create_all(engine)