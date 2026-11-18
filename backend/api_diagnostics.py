"""Provider and routing diagnostics with explicit evidence boundaries."""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import DNSEvent, Device
from db.session import get_db
from discovery.service import get_local_network_info
from dns.providers.errors import ProviderError, STATE_MESSAGES
from dns.providers.registry import provider_filtering, provider_statistics, provider_status
from enforcement.adapter import DNSBackendAdapter

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


def _provider_call(fn):
    try:
        return {"available": True, "data": fn()}
    except ProviderError as error:
        return {
            "available": False,
            "state": error.state,
            "message": STATE_MESSAGES.get(error.state, str(error)),
            "data": None,
        }
    except Exception:
        return {
            "available": False,
            "state": "unavailable",
            "message": "The provider did not return a usable response.",
            "data": None,
        }


@router.get("/adguard")
def adguard_diagnostics(
    subnet: Optional[str] = None,
    device_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    status = provider_status()
    filtering = _provider_call(provider_filtering)
    statistics = _provider_call(provider_statistics)
    adapter = DNSBackendAdapter()

    query = db.query(DNSEvent)
    if subnet:
        query = query.join(DNSEvent.device).filter(Device.network_subnet == subnet)
    if device_id is not None:
        query = query.filter(DNSEvent.device_id == device_id)
    recorded_events = query.count()
    linked_events = query.filter(DNSEvent.device_id.is_not(None)).count()
    latest = query.order_by(DNSEvent.query_timestamp.desc()).first()

    local = get_local_network_info()
    return {
        "provider": {
            "configured": status.get("state") not in (None, "not_configured"),
            "state": status.get("state"),
            "provider": status.get("provider"),
            "version": status.get("version"),
            "authentication": status.get("authentication"),
            "capabilities": status.get("capabilities", []),
            "unsupported": status.get("unsupported", []),
            "message": status.get("message"),
            "config": status.get("config"),
        },
        "filtering": filtering,
        "statistics": statistics,
        "enforcement": {
            "backend": adapter.backend,
            "enabled": adapter.enabled,
            "available": adapter.available(),
        },
        "query_log": {
            "recorded_events": recorded_events,
            "linked_events": linked_events,
            "latest_timestamp": (
                latest.query_timestamp.isoformat() if latest is not None else None
            ),
            "clients_identifiable": linked_events > 0,
        },
        "router": {
            "interface": local.get("interface"),
            "local_ip": local.get("ip_address"),
            "gateway": local.get("gateway"),
            "dhcp_dns_verified": False,
            "dns_redirect_verified": False,
            "note": (
                "Router DHCP/DNS configuration has not been independently verified by Netra. "
                "Only provider-level functionality can be shown here."
            ),
        },
        "scope": {
            "subnet": subnet,
            "device_id": device_id,
            "laptop_local_monitoring": True,
            "router_wide_protection_verified": False,
        },
    }
