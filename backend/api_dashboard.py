"""Single-call dashboard aggregation using existing backend data sources."""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api_bandwidth import status as bandwidth_status
from api_discovery import discovery_status
from api_enforcement import readiness as enforcement_readiness
from db.models import AuditReport, Device, DNSEvent
from db.session import get_db
from dns.analytics import summary as dns_summary
from dns.providers.registry import provider_status
from privacy.scoring import privacy_score

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(subnet: Optional[str] = None, db: Session = Depends(get_db)):
    device_query = db.query(Device)
    if subnet:
        device_query = device_query.filter(Device.network_subnet == subnet)
    else:
        device_query = device_query.filter(Device.is_current.is_(True))
    devices = device_query.all()

    dns = dns_summary(db, device_id=None, subnet=subnet, since=None)
    dns_events = db.query(DNSEvent)
    if subnet:
        dns_events = dns_events.join(DNSEvent.device).filter(
            Device.network_subnet == subnet
        )
    score = privacy_score([{"category": event.category} for event in dns_events.all()])

    audit_query = db.query(AuditReport)
    if subnet:
        audit_query = audit_query.filter(AuditReport.network_subnet == subnet)
    latest_audit = audit_query.order_by(AuditReport.created_at.desc()).first()
    provider = provider_status()
    readiness = enforcement_readiness(db)
    bandwidth = bandwidth_status(interface=None, db=db)
    discovery = discovery_status(subnet=subnet) if subnet else discovery_status()

    return {
        "selected_subnet": subnet,
        "devices": {
            "count": len(devices),
            "scope": "selected subnet" if subnet else "latest discovery snapshot",
        },
        "discovery": discovery,
        "dns": {
            "total": dns.get("total", 0),
            "allowed": dns.get("allowed", 0),
            "blocked": dns.get("blocked", 0),
            "blocking_percentage": dns.get("blocking_percentage"),
            "unknown_blocked_status": dns.get("unknown_blocked_status", 0),
            "available": True,
        },
        "provider": {
            "configured": provider.get("state") != "not_configured",
            "state": provider.get("state"),
            "provider": provider.get("provider"),
            "message": provider.get("message"),
        },
        "privacy": {
            "score": score.get("score"),
            "explanation": score.get("explanation"),
            "tracking_events": score.get("tracking_events"),
            "unknown_events": score.get("unknown_events"),
            "latest_audit_id": latest_audit.id if latest_audit else None,
            "latest_audit_created_at": (
                latest_audit.created_at.isoformat() if latest_audit else None
            ),
            "latest_audit_scope": latest_audit.scope if latest_audit else None,
        },
        "enforcement": {
            "provider_ready": readiness["provider_ready"],
            "network_wide_ready": readiness["network_wide_ready"],
            "state": readiness["provider_state"],
            "snapshot_count": readiness["snapshot_count"],
        },
        "bandwidth": {
            "available": True,
            "interface": bandwidth["interface"],
            "scope": bandwidth["scope"],
            "rx_bytes_per_second": (bandwidth.get("latest") or {}).get(
                "rx_bytes_per_second"
            ),
            "tx_bytes_per_second": (bandwidth.get("latest") or {}).get(
                "tx_bytes_per_second"
            ),
            "rx_bytes_total": bandwidth["cumulative"]["rx_bytes"],
            "tx_bytes_total": bandwidth["cumulative"]["tx_bytes"],
            "sample_count": bandwidth["sample_count"],
        },
    }
