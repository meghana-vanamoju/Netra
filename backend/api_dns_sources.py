from fastapi import APIRouter

from dns.providers.registry import provider_status

router = APIRouter(prefix="/api/dns/sources", tags=["dns-sources"])


@router.get("/status")
def status():
    """Legacy source status shape plus real provider state (additive fields)."""
    report = provider_status()
    return {
        "available": report["state"] == "healthy",
        "collected": 0,
        "state": report["state"],
        "provider": report.get("provider"),
        "message": report.get("message"),
        "capabilities": report.get("capabilities", []),
        "unsupported": report.get("unsupported", []),
    }
