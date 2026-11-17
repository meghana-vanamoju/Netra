from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.models import DNSEvent, Device
from db.session import get_db
from dns.analytics import classify_domain, ingest_event, summary
from dns.providers.errors import ProviderError, STATE_MESSAGES
from dns.providers.registry import (
    fetch_provider_queries,
    provider_filtering,
    provider_statistics,
    provider_status,
)

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
    if ev is None:
        raise HTTPException(400, "Invalid DNS event")
    return {"id": ev.id, "domain": ev.domain, "category": ev.category}


@router.get("/providers/status")
def dns_provider_status():
    return provider_status()


def _provider_error_response(error):
    return HTTPException(
        status_code=503,
        detail={
            "state": error.state,
            "message": STATE_MESSAGES.get(error.state, str(error)),
        },
    )


@router.get("/providers/statistics")
def dns_provider_statistics():
    try:
        return provider_statistics()
    except ProviderError as error:
        raise _provider_error_response(error) from None


@router.get("/providers/filtering")
def dns_provider_filtering():
    try:
        return provider_filtering()
    except ProviderError as error:
        raise _provider_error_response(error) from None


@router.post("/events/sync")
def sync_events(db: Session = Depends(get_db), limit: Optional[int] = None):
    """Fetch real provider queries and store them idempotently.

    Provider failures are reported as a sanitized 503 with the provider state,
    never as a healthy empty result.
    """
    status = provider_status()
    if status["state"] != "healthy":
        raise HTTPException(
            status_code=503,
            detail={
                "state": status["state"],
                "message": STATE_MESSAGES.get(status["state"], status["state"]),
                "provider": status.get("provider"),
            },
        )
    try:
        records = fetch_provider_queries()
    except ProviderError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "state": error.state,
                "message": STATE_MESSAGES.get(error.state, str(error)),
            },
        ) from None
    from dns.analytics import ingest_events

    result = ingest_events(db, records, source=status.get("provider") or "provider")
    return {
        "provider": status.get("provider"),
        "fetched": len(records),
        "inserted": result["inserted"],
        "duplicates": result["duplicates"],
        "skipped": result["skipped"],
        "state": "healthy",
    }


@router.get("/events")
def list_events(
    limit: int = 50,
    offset: int = 0,
    device_id: Optional[int] = None,
    blocked: Optional[bool] = None,
    source: Optional[str] = None,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    query = db.query(DNSEvent)
    if device_id:
        query = query.filter(DNSEvent.device_id == device_id)
    if blocked is not None:
        query = query.filter(DNSEvent.blocked == (1 if blocked else 0))
    if source:
        query = query.filter(DNSEvent.source == source)
    events = (
        query.order_by(DNSEvent.query_timestamp.desc()).offset(offset).limit(limit).all()
    )
    return [
        {
            "id": event.id,
            "domain": event.domain,
            "category": event.category,
            "device_id": event.device_id,
            "timestamp": event.query_timestamp,
            "query_type": event.query_type,
            "blocked": bool(event.blocked) if event.blocked is not None else None,
            "client": event.client,
            "client_name": event.client_name,
            "reason": event.reason,
            "rules": event.rules_json or [],
            "upstream": event.upstream,
            "source": event.source or "manual",
            "confidence": event.confidence,
        }
        for event in events
    ]


@router.get("/analytics/summary")
def analytics_summary(
    device_id: Optional[int] = None,
    since: Optional[str] = None,
    db: Session = Depends(get_db),
):
    parsed = None
    if since:
        try:
            parsed = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "Invalid since timestamp") from None
    return summary(db, device_id=device_id, since=parsed)


@router.get("/analytics/domains")
def top_domains(limit: int = 10, db: Session = Depends(get_db)):
    from sqlalchemy import func
    rows = (
        db.query(DNSEvent.domain, func.count(DNSEvent.id))
        .group_by(DNSEvent.domain)
        .order_by(func.count(DNSEvent.id).desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return [
        {
            "domain": row[0],
            "count": row[1],
            "category": classify_domain(row[0])[0],
            "evidence": classify_domain(row[0])[1],
        }
        for row in rows
    ]


@router.get("/analytics/devices")
def by_device(db: Session = Depends(get_db)):
    from sqlalchemy import func
    rows = (
        db.query(DNSEvent.device_id, func.count(DNSEvent.id))
        .group_by(DNSEvent.device_id)
        .all()
    )
    return [{"device_id": row[0], "count": row[1]} for row in rows]


@router.get("/analytics/clients")
def by_client(db: Session = Depends(get_db)):
    from sqlalchemy import func
    rows = (
        db.query(DNSEvent.client, func.count(DNSEvent.id))
        .group_by(DNSEvent.client)
        .order_by(func.count(DNSEvent.id).desc())
        .limit(20)
        .all()
    )
    return [{"client": row[0] or "unknown", "count": row[1]} for row in rows]
