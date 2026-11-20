from datetime import datetime
import hashlib
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.models import DNSEvent, Device, ConfigSnapshot
from db.session import get_db
from dns.analytics import classify_domain, ingest_event, summary
from dns.journal import enrich_from_journal
from dns.providers.errors import ProviderError, STATE_MESSAGES
from dns.providers.registry import (
    fetch_provider_queries,
    provider_filtering,
    provider_statistics,
    provider_status,
    refresh_provider_filters,
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


class FilteringRuleIn(BaseModel):
    domain: str
    action: str = "block"
    confirm: bool = False


class FilterRefreshIn(BaseModel):
    confirm: bool = False


@router.post("/providers/filtering/rules")
def set_provider_filtering_rule(
    payload: FilteringRuleIn, db: Session = Depends(get_db)
):
    if not payload.confirm:
        raise HTTPException(400, "Explicit confirmation required")
    if payload.action not in {"block", "unblock", "allow", "remove"}:
        raise HTTPException(400, "Action must be block, unblock, allow, or remove")
    from enforcement.adapter import DNSBackendAdapter

    adapter = DNSBackendAdapter()
    if not adapter.available():
        raise HTTPException(503, "DNS provider not configured")
    if not adapter.enabled:
        raise HTTPException(503, "DNS enforcement is disabled")
    if adapter.backend != "adguard":
        raise HTTPException(
            501, "Filtering rule changes are supported only for AdGuard Home"
        )

    try:
        prior = adapter.provider.filtering_status()
    except Exception:
        raise HTTPException(
            503,
            "Could not capture provider rule state; no rule change was made",
        ) from None
    if not isinstance(prior.get("user_rules"), list):
        raise HTTPException(
            503,
            "Could not capture provider rule state; no rule change was made",
        )

    state = {
        "provider": "adguard-home",
        "user_rules": prior["user_rules"],
        "operation": payload.action,
        "domain": payload.domain,
    }
    raw = json.dumps(state, sort_keys=True)
    snapshot = ConfigSnapshot(
        backend="adguard-home",
        state_json=state,
        checksum=hashlib.sha256(raw.encode()).hexdigest(),
        policy_id=None,
    )
    try:
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
    except Exception:
        db.rollback()
        raise HTTPException(
            503,
            "Could not snapshot provider rule state; no rule change was made",
        ) from None

    try:
        if payload.action == "block":
            result = adapter.provider.add_user_rule(payload.domain)
        elif payload.action == "allow":
            result = adapter.provider.add_user_rule(payload.domain, action="allow")
        else:
            result = adapter.provider.remove_user_rule(payload.domain)
        result["snapshot_id"] = snapshot.id
        result["rollback_available"] = True
        return result
    except ProviderError as error:
        raise HTTPException(
            503,
            {
                "state": error.state,
                "message": STATE_MESSAGES.get(error.state, str(error)),
                "snapshot_id": snapshot.id,
                "rollback_available": True,
                "operation_applied": False,
            },
        ) from None
    except ValueError as error:
        raise HTTPException(
            400,
            {
                "message": str(error),
                "snapshot_id": snapshot.id,
                "rollback_available": True,
                "operation_applied": False,
            },
        ) from None


@router.post("/providers/filtering/refresh")
def refresh_filtering(payload: FilterRefreshIn):
    if not payload.confirm:
        raise HTTPException(400, "Explicit confirmation required")
    from enforcement.adapter import DNSBackendAdapter

    adapter = DNSBackendAdapter()
    if not adapter.available():
        raise HTTPException(503, "DNS provider not configured")
    if adapter.backend != "adguard":
        raise HTTPException(
            501, "Filter refresh is supported only for AdGuard Home"
        )
    try:
        return refresh_provider_filters()
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
    # Best-effort, copied-record enrichment. Source IDs and AdGuard filtering
    # metadata are untouched; journal failure never blocks a normal sync.
    records, _correlation = enrich_from_journal(records)

    from dns.analytics import ingest_events

    result = ingest_events(db, records, source=status.get("provider") or "provider")
    response = {
        "provider": status.get("provider"),
        "fetched": len(records),
        "inserted": result["inserted"],
        "duplicates": result["duplicates"],
        "skipped": result["skipped"],
        "state": "healthy",
    }
    # Keep the original response shape unless journal evidence was actually
    # available. Ambiguity is surfaced only when it can affect an event.
    if _correlation.get("candidates") or _correlation.get("ambiguous"):
        response["correlation"] = {
            key: _correlation.get(key, 0)
            for key in (
                "candidates",
                "enriched",
                "already_matched",
                "ambiguous",
                "unmatched",
            )
        }
    return response


@router.get("/events")
def list_events(
    limit: int = 50,
    offset: int = 0,
    device_id: Optional[int] = None,
    blocked: Optional[bool] = None,
    source: Optional[str] = None,
    linked: Optional[bool] = Query(None),
    client_ip: Optional[str] = Query(None),
    subnet: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
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
    if linked is True:
        query = query.filter(DNSEvent.device_id.is_not(None))
    if linked is False:
        query = query.filter(DNSEvent.device_id.is_(None))
    if client_ip:
        query = query.filter(DNSEvent.client == client_ip.strip())
    if domain:
        query = query.filter(DNSEvent.domain == domain.strip().lower())
    if subnet:
        device_ids = [
            row[0]
            for row in db.query(Device.id)
            .filter(Device.network_subnet == subnet.strip())
            .all()
        ]
        if device_ids:
            query = query.filter(DNSEvent.device_id.in_(device_ids))
        else:
            query = query.filter(False)
    events = (
        query.order_by(DNSEvent.query_timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    devices_by_id = (
        {
            device.id: device
            for device in db.query(Device)
            .filter(
                Device.id.in_([event.device_id for event in events if event.device_id])
            )
            .all()
        }
        if events
        else {}
    )
    return [
        {
            "id": event.id,
            "domain": event.domain,
            "category": event.category,
            "device_id": event.device_id,
            "device": (
                {
                    "name": devices_by_id[event.device_id].hostname,
                    "ip": devices_by_id[event.device_id].ip_address,
                    "mac": (
                        devices_by_id[event.device_id].mac_address.upper()
                        if devices_by_id[event.device_id].mac_address
                        else None
                    ),
                }
                if event.device_id in devices_by_id
                else None
            ),
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
            "association_status": event.association_status
            or ("linked" if event.device_id else "unlinked"),
        }
        for event in events
    ]


@router.get("/analytics/summary")
def analytics_summary(
    device_id: Optional[int] = None,
    subnet: Optional[str] = None,
    since: Optional[str] = None,
    db: Session = Depends(get_db),
):
    parsed = None
    if since:
        try:
            parsed = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "Invalid since timestamp") from None
    return summary(db, device_id=device_id, subnet=subnet, since=parsed)


@router.get("/analytics/domains")
def top_domains(
    limit: int = 10,
    device_id: Optional[int] = None,
    subnet: Optional[str] = None,
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    query = db.query(DNSEvent.domain, func.count(DNSEvent.id))
    if device_id:
        query = query.filter(DNSEvent.device_id == device_id)
    if subnet:
        device_ids = [
            row[0]
            for row in db.query(Device.id)
            .filter(Device.network_subnet == subnet.strip())
            .all()
        ]
        if device_ids:
            query = query.filter(DNSEvent.device_id.in_(device_ids))
        else:
            query = query.filter(False)
    rows = (
        query.group_by(DNSEvent.domain)
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
def by_device(subnet: Optional[str] = None, db: Session = Depends(get_db)):
    from sqlalchemy import func

    query = db.query(
        DNSEvent.device_id,
        func.count(DNSEvent.id),
        func.sum(DNSEvent.blocked == 1),
        func.sum(DNSEvent.blocked == 0),
    )
    if subnet:
        device_ids = [
            row[0]
            for row in db.query(Device.id)
            .filter(Device.network_subnet == subnet.strip())
            .all()
        ]
        if device_ids:
            query = query.filter(DNSEvent.device_id.in_(device_ids))
        else:
            query = query.filter(False)
    rows = query.group_by(DNSEvent.device_id).all()
    return [
        {
            "device_id": row[0],
            "count": row[1],
            "blocked": int(row[2] or 0),
            "allowed": int(row[3] or 0),
        }
        for row in rows
    ]


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
