from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db
from db.models import Device
from classification.engine import classify

router = APIRouter(prefix="/api", tags=["classification"])

@router.get("/devices/{device_id}/classification")
def get_classification(device_id: int, db: Session = Depends(get_db)):
    d = db.get(Device, device_id)
    if not d:
        raise HTTPException(404, "Device not found")
    return {"device_id": device_id, **classify(d)}

@router.post("/devices/{device_id}/classify")
def classify_now(device_id: int, db: Session = Depends(get_db)):
    d = db.get(Device, device_id)
    if not d:
        raise HTTPException(404, "Device not found")
    return {"device_id": device_id, **classify(d)}

@router.get("/classifications")
def list_classifications(db: Session = Depends(get_db)):
    out = []
    for d in db.query(Device).all():
        out.append({"device_id": d.id, **classify(d)})
    return out