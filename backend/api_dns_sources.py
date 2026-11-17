from fastapi import APIRouter
from dns.sources.base import DNSSource

router = APIRouter(prefix="/api/dns/sources", tags=["dns-sources"])

@router.get("/status")
def status():
    src = DNSSource()
    return {"available": src.available(), "collected": len(src.collect())}