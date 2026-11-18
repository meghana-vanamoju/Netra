from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.session import get_db
from db.models import DNSEvent, Device
from privacy.scoring import privacy_score

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


@router.get("/score")
def score(subnet: Optional[str] = None, device_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(DNSEvent)
    if subnet:
        query = query.join(DNSEvent.device).filter(Device.network_subnet == subnet)
    if device_id is not None:
        query = query.filter(DNSEvent.device_id == device_id)
    events = query.all()
    data = [{"category": event.category} for event in events]
    result = privacy_score(data)
    result["observed_events"] = len(events)
    result["scope"] = {
        "subnet": subnet,
        "device_id": device_id,
    }
    return result
