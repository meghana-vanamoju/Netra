from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.session import get_db
from db.models import DNSEvent
from privacy.scoring import privacy_score

router = APIRouter(prefix="/api/privacy", tags=["privacy"])

@router.get("/score")
def score(db: Session = Depends(get_db)):
    evs = db.query(DNSEvent).all()
    data = [{"category": e.category} for e in evs]
    return privacy_score(data)