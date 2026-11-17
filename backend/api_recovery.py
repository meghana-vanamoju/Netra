from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.models import Policy, PolicyExecution
from db.session import get_db

router = APIRouter(prefix="/api/recovery", tags=["recovery"])


@router.get("/status")
def status(db: Session = Depends(get_db)):
    interrupted = db.query(Policy).filter(Policy.status == "applying").count()
    failures = (
        db.query(PolicyExecution).filter(PolicyExecution.status == "failed").count()
    )
    return {
        "recovery_ready": interrupted == 0,
        "interrupted_executions": interrupted,
        "failed_executions": failures,
    }
