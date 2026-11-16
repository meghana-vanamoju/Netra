from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import get_database_url

_engine = None
_SessionLocal = None

def get_engine():
    global _engine
    if _engine is None:
        url = get_database_url()
        _engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    return _engine

def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal

def get_db():
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from .models import Base
    Base.metadata.create_all(bind=get_engine())