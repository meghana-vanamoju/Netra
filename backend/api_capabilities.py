import os

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.session import get_db
from dns.providers.registry import provider_status

router = APIRouter(prefix="/api/backend", tags=["capabilities"])


@router.get("/capabilities")
def capabilities():
    report = provider_status()
    return {
        "configured_backend": os.environ.get("NETRA_DNS_BACKEND"),
        "available": report["state"] == "healthy",
        "status": "ok" if report["state"] == "healthy" else report["state"],
        "provider": report.get("provider"),
        "provider_state": report["state"],
        "capabilities": report.get("capabilities", []),
        "unsupported": report.get("unsupported", []),
    }


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "ok"}
