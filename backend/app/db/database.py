from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _build_connect_args(database_url: str) -> dict[str, bool]:
    connect_args: dict[str, bool] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return connect_args


def build_engine(database_url: str):
    engine = create_engine(
        database_url,
        connect_args=_build_connect_args(database_url),
    )
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


engine = build_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(backend_root() / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root() / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url or settings.database_url)
    return config


def run_migrations(
    revision: str = "head",
    *,
    database_url: str | None = None,
) -> None:
    command.upgrade(get_alembic_config(database_url), revision)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Fast metadata bootstrap kept only as a development/test escape hatch.

    Production and normal local startup should use Alembic migrations instead.
    """
    from app.models import Base  # noqa: PLC0415

    Base.metadata.create_all(bind=engine)


def reset_db() -> None:
    """Fast test reset helper that bypasses Alembic for unit-style tests."""
    from app.models import Base  # noqa: PLC0415

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
