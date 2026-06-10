"""SQLite engine + session. sqlite-vec is loaded when available for fast
vector search; otherwise search falls back to in-Python cosine (fine for a
single user's diary)."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

engine = create_engine(
    f"sqlite:///{settings.DATABASE_PATH}",
    connect_args={"check_same_thread": False},
)

VEC_AVAILABLE = False
try:
    import sqlite_vec  # noqa: F401

    VEC_AVAILABLE = True

    @event.listens_for(engine, "connect")
    def _load_vec(dbapi_conn, _):
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)

except (ImportError, AttributeError):
    pass

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)
    _migrate()


def _migrate() -> None:
    """Tiny additive migrations for existing databases (SQLite ALTER only)."""
    from sqlalchemy import text

    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(entries)"))}
        if "mood" not in cols:
            conn.execute(text("ALTER TABLE entries ADD COLUMN mood INTEGER"))
