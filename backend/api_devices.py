from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime

from db.session import get_db
from db.models import Device
from schemas import DeviceCreate, DeviceOut

router = APIRouter(prefix="/api/devices", tags=["devices"])


def _norm(v):
    return v.strip().lower() if v else None


@router.get("", response_model=list[DeviceOut])
def list_devices(
    ip: str | None = Query(None),
    hostname: str | None = Query(None),
    vendor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Device)
    if ip:
        q = q.filter(Device.ip_address == ip.strip())
    if hostname:
        q = q.filter(Device.hostname.ilike(f"%{hostname}%"))
    if vendor:
        q = q.filter(Device.vendor == vendor)
    return q.offset(offset).limit(limit).all()


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, db: Session = Depends(get_db)):
    d = db.get(Device, device_id)
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    return d


@router.post("", response_model=DeviceOut, status_code=201)
def register_device(payload: DeviceCreate, db: Session = Depends(get_db)):
    mac = _norm(payload.mac_address)
    # identity matching: prefer MAC if available
    existing = None
    if mac:
        existing = (
            db.query(Device)
            .filter(func.upper(Device.mac_address) == mac.upper())
            .first()
        )
    if not existing and payload.ip_address:
        existing = (
            db.query(Device)
            .filter(Device.ip_address == payload.ip_address.strip())
            .first()
        )

    if existing:
        existing.ip_address = payload.ip_address.strip()
        existing.mac_address = mac or existing.mac_address
        existing.hostname = (
            payload.hostname if payload.hostname is not None else existing.hostname
        )
        existing.vendor = (
            payload.vendor if payload.vendor is not None else existing.vendor
        )
        existing.discovery_source = (
            payload.discovery_source or existing.discovery_source
        )
        if payload.metadata is not None:
            existing.extra = payload.metadata
        existing.last_seen = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    d = Device(
        ip_address=payload.ip_address.strip(),
        mac_address=mac,
        hostname=payload.hostname,
        vendor=payload.vendor,
        discovery_source=payload.discovery_source,
        extra=payload.metadata,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.delete("/{device_id}", status_code=204)
def delete_device(device_id: int, db: Session = Depends(get_db)):
    d = db.get(Device, device_id)
    if not d:
        raise HTTPException(status_code=404, detail="Device not found")
    db.delete(d)
    db.commit()
    return None
