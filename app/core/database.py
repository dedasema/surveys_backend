from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

is_sqlite = settings.sync_database_url.startswith("sqlite")

engine_kwargs = {
    "echo": False,
    "future": True,
}

if not is_sqlite:
    engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 10
    })
else:
    engine_kwargs.update({
        "connect_args": {"check_same_thread": False}
    })

engine = create_engine(settings.sync_database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
