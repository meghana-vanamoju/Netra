from fastapi import APIRouter
from enforcement.adapter import DNSBackendAdapter

router = APIRouter(prefix="/api/enforcement", tags=["enforcement"])

@router.get("/status")
def status():
    ad = DNSBackendAdapter()
    return {"available": ad.available(), "backend": ad.backend}