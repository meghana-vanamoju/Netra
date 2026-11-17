from fastapi import APIRouter

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
