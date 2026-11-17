from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db

router = APIRouter(prefix="/api/verification", tags=["verification"])

@router.get("/policy/{policy_id}")
def verify_policy(policy_id: int, db: Session = Depends(get_db)):
    return {"policy_id": policy_id, "status": "not_verified", "reason": "No backend configured"}