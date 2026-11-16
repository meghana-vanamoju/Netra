from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
import os
from db.session import get_db
from db.models import Device
from discovery.service import discover_subnet, validate_subnet
from schemas import DeviceCreate

router = APIRouter(prefix="/api/discovery", tags=["discovery"])
_results = []

@router.post("/run")
def run_discovery(subnet: str = "192.168.1.0/24", db: Session = Depends(get_db)):
    global _results
    try:
        validate_subnet(subnet)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    discovered = discover_subnet(subnet)
    _results = discovered
    # register
    for d in discovered:
        mac = d.get("mac_address")
        existing = None
        if mac:
            existing = db.query(Device).filter(Device.mac_address == mac).first()
        if not existing:
            existing = db.query(Device).filter(Device.ip_address == d["ip_address"]).first()
        if existing:
            existing.ip_address = d["ip_address"]
            existing.hostname = d.get("hostname") or existing.hostname
            existing.discovery_source = "lan-discovery"
            db.commit()
        else:
            dev = Device(ip_address=d["ip_address"], mac_address=mac, hostname=d.get("hostname"), discovery_source="lan-discovery")
            db.add(dev)
            db.commit()
    return {"discovered": len(discovered), "subnet": subnet}

@router.get("/results")
def results():
    return _results