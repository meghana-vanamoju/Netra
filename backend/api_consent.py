import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db
from db.models import Policy, PolicyExecution, DryRunPlan

router = APIRouter(prefix="/api/policies", tags=["consent"])

VALID_TRANSITIONS = {
    "proposed": {"dry-run completed"},
    "dry-run completed": {"awaiting approval"},
    "awaiting approval": {"approved"},
    "approved": {"applying"},
    "applying": {"applied", "failed"},
    "applied": {"reverted"},
}

def transition(p, new):
    allowed = VALID_TRANSITIONS.get(p.status, set())
    if new not in allowed:
        raise HTTPException(400, f"Invalid transition {p.status} -> {new}")
    p.status = new

@router.post("/{policy_id}/approve")
def approve(policy_id: int, plan_id: int, approver: str = "local-user", confirm: bool = False, db: Session = Depends(get_db)):
    p = db.get(Policy, policy_id)
    if not p:
        raise HTTPException(404, "Policy not found")
    plan = db.get(DryRunPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Dry-run plan not found")
    if not confirm:
        raise HTTPException(400, "Explicit confirmation required")
    p.dry_run_plan_id = plan_id
    p.approver = approver
    from datetime import datetime
    p.approved_at = datetime.utcnow()
    transition(p, "approved")
    db.commit()
    return {"status": "approved", "policy_id": policy_id}

@router.get("/{policy_id}/approval")
def approval(policy_id: int, db: Session = Depends(get_db)):
    p = db.get(Policy, policy_id)
    if not p:
        raise HTTPException(404, "Policy not found")
    return {"status": p.status, "approver": p.approver, "approved_at": p.approved_at, "plan_id": p.dry_run_plan_id}

@router.post("/{policy_id}/apply")
def apply(policy_id: int, db: Session = Depends(get_db)):
    p = db.get(Policy, policy_id)
    if not p:
        raise HTTPException(404, "Policy not found")
    if p.status != "approved":
        raise HTTPException(400, "Policy not approved")
    backend = os.environ.get("NETRA_DNS_BACKEND")
    if not backend:
        ex = PolicyExecution(policy_id=policy_id, status="failed", details={"error": "No DNS backend configured"})
        db.add(ex); db.commit()
        raise HTTPException(503, "DNS backend not configured")
    transition(p, "applying")
    db.commit()
    # mock backend application would happen here; keep unavailable path
    ex = PolicyExecution(policy_id=policy_id, status="failed", details={"error": "Backend integration not implemented"})
    db.add(ex); db.commit()
    transition(p, "failed")
    db.commit()
    return {"status": "failed", "reason": "Backend integration not implemented"}

@router.get("/{policy_id}/execution")
def execution(policy_id: int, db: Session = Depends(get_db)):
    ex = db.query(PolicyExecution).filter(PolicyExecution.policy_id == policy_id).order_by(PolicyExecution.created_at.desc()).first()
    if not ex:
        raise HTTPException(404, "No execution record")
    return {"status": ex.status, "details": ex.details}

@router.get("/{policy_id}/rollback-status")
def rollback_status(policy_id: int, db: Session = Depends(get_db)):
    p = db.get(Policy, policy_id)
    if not p:
        raise HTTPException(404, "Policy not found")
    return {"policy_id": policy_id, "status": p.status, "rollback_ready": p.status in ("applied", "failed")}