from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.models import ConfigSnapshot
from db.session import get_db
from discovery.service import get_local_network_info
from dns.providers.registry import provider_status
from enforcement.adapter import DNSBackendAdapter

router = APIRouter(prefix="/api/enforcement", tags=["enforcement"])


@router.get("/status")
def status():
    adapter = DNSBackendAdapter()
    report = provider_status()
    return {
        "available": adapter.available(),
        "backend": adapter.backend,
        "enabled": adapter.enabled,
        "provider_state": report["state"],
    }


@router.get("/readiness")
def readiness(db: Session = Depends(get_db)):
    """Describe verified capabilities without performing any network change."""
    adapter = DNSBackendAdapter()
    report = provider_status()
    local = get_local_network_info()
    snapshot_count = db.query(ConfigSnapshot).count()
    filtering_available = "filtering" in report.get("capabilities", [])
    provider_ready = (
        report.get("state") == "healthy"
        and adapter.available()
        and adapter.enabled
        and filtering_available
    )
    return {
        "provider_ready": provider_ready,
        "network_wide_ready": False,
        "provider_state": report.get("state"),
        "backend": adapter.backend,
        "enabled": adapter.enabled,
        "filtering_available": filtering_available,
        "snapshot_count": snapshot_count,
        "local_network": local,
        "required_permissions": [
            "Read local interface counters for host-level monitoring",
            "Configured DNS provider API credentials for provider-level changes",
            "Explicit DNS enforcement opt-in and per-action confirmation",
        ],
        "supported_modes": [
            {
                "mode": "provider_dns_filtering",
                "supported": filtering_available,
                "scope": "DNS provider server",
            },
            {
                "mode": "provider_configuration_snapshot_rollback",
                "supported": snapshot_count > 0,
                "scope": "provider user rules",
            },
        ],
        "unsupported_modes": [
            {"mode": "router_dhcp_dns_configuration", "reason": "No verified router management write capability"},
            {"mode": "internet_access_firewall_controls", "reason": "No firewall adapter is configured"},
            {"mode": "schedule_based_policy_enforcement", "reason": "No scheduler is configured"},
            {"mode": "encrypted_dns_bypass_prevention", "reason": "Not verifiable from provider or host data"},
        ],
        "warnings": [
            "Provider filtering is server-side and does not prove router-wide or client-level enforcement.",
            "Router DHCP/DNS settings are never changed automatically by Netra.",
            "Apply and rollback require explicit confirmation and real provider evidence.",
        ],
    }
