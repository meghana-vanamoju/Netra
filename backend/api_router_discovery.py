from fastapi import APIRouter, HTTPException
from discovery.router.adapter import validate_router_ip, RouterAdapter

router = APIRouter(prefix="/api/router", tags=["router"])

@router.post("/test")
def test_router(ip: str):
    if not validate_router_ip(ip):
        raise HTTPException(400, "Invalid IP")
    ad = RouterAdapter(ip)
    return {"ip": ip, "reachable": ad.reachable()}

@router.get("/capabilities")
def caps(ip: str):
    if not validate_router_ip(ip):
        raise HTTPException(400, "Invalid IP")
    return RouterAdapter(ip).capabilities()