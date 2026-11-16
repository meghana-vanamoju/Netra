from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from db.session import get_db
from db.models import DNSEvent, Device
from dns.analytics import classify_domain, ingest_event, summary

router = APIRouter(prefix="/api/dns", tags=["dns"])

class DNSEventIn(BaseModel):
    domain: str
    query_type: Optional[str] = None
    source_ip: Optional[str] = None
    blocked: Optional[bool] = None

@router.post("/events")
def create_event(payload: DNSEventIn, db: Session = Depends(get_db)):
    if not payload.domain or "." not in payload.domain:
        raise HTTPException(400, "Invalid domain")
    ev = ingest_event(db, payload.dict())
    return {"id": ev.id, "domain": ev.domain, "category": ev.category}

@router.get("/events")
def list_events(limit: int = 50, offset: int = 0, device_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(DNSEvent)
    if device_id:
        q = q.filter(DNSEvent.device_id == device_id)
    evs = q.order_by(DNSEvent.query_timestamp.desc()).offset(offset).limit(limit).all()
    return [{"id": e.id, "domain": e.domain, "category": e.category, "device_id": e.device_id, "timestamp": e.query_timestamp} for e in evs]

@router.get("/analytics/summary")
def analytics_summary(device_id: Optional[int] = None, db: Session = Depends(get_db)):
    return summary(db, device_id=device_id)

@router.get("/analytics/domains")
def top_domains(limit: int = 10, db: Session = Depends(get_db)):
    from sqlalchemy import func
    rows = db.query(DNSEvent.domain, func.count(DNSEvent.id)).group_by(DNSEvent.domain).order_by(func.count(DNSEvent.id).desc()).limit(limit).all()
    return [{"domain": r[0], "count": r[1], "category": classify_domain(r[0])[0]} for r in rows]

@router.get("/analytics/devices")
def by_device(db: Session = Depends(get_db)):
    from sqlalchemy import func
    rows = db.query(DNSEvent.device_id, func.count(DNSEvent.id)).group_by(DNSEvent.device_id).all()
    return [{"device_id": r[0], "count": r[1]} for r in rows]