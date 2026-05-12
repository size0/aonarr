"""数据库连接管理"""
import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/
DATA_DIR = Path(os.getenv("NOVELFORGE_DATA_DIR", str(_BACKEND_ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'novelforge.db'}")

_is_sqlite = DB_URL.startswith("sqlite")

engine = create_engine(
    DB_URL,
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
    pool_pre_ping=True,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Session:
    """FastAPI Depends 用的数据库会话生成器"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有表（开发用，生产用 Alembic）"""
    Base.metadata.create_all(bind=engine)
