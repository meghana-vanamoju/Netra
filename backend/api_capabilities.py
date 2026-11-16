from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.session import get_db

router = APIRouter(prefix="/api/backend", tags=["capabilities"])

@router.get("/capabilities")
def capabilities():
    import os
    backend = os.environ.get("NETRA_DNS_BACKEND")
    return {"configured_backend": backend, "available": bool(backend), "status": "ok" if backend else "unavailable"}

@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(__import__("sqlalchemy").text("SELECT 1"))
    return {"database": "ok"}