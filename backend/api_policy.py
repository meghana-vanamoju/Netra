from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db
from db.models import Policy, DryRunPlan, AuditReport
from policy.engine import generate_policies, dry_run

router = APIRouter(prefix="/api/policies", tags=["policy"])

@router.post("/plan")
def plan(audit_id: int, db: Session = Depends(get_db)):
    rep = db.get(AuditReport, audit_id)
    if not rep:
        raise HTTPException(404, "Audit not found")
    policies = generate_policies(db, rep.findings_json or [])
    return {"policies": [p.id for p in policies]}

@router.get("")
def list_policies(db: Session = Depends(get_db)):
    ps = db.query(Policy).all()
    return [{"id": p.id, "name": p.name, "risk": p.risk, "status": p.status} for p in ps]

@router.get("/{policy_id}")
def get_policy(policy_id: int, db: Session = Depends(get_db)):
    p = db.get(Policy, policy_id)
    if not p:
        raise HTTPException(404, "Policy not found")
    return {"id": p.id, "name": p.name, "action": p.action, "risk": p.risk, "reversible": bool(p.reversible)}

@router.post("/dry-run")
def run_dry(policy_ids: list[int], db: Session = Depends(get_db)):
    dr, plan, impact = dry_run(db, policy_ids)
    return {"plan_id": dr.id, "plan": plan, "impact": impact}

@router.get("/dry-run/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    dr = db.get(DryRunPlan, plan_id)
    if not dr:
        raise HTTPException(404, "Plan not found")
    return {"id": dr.id, "plan": dr.plan_json}

@router.get("/dry-run/{plan_id}/impact")
def get_impact(plan_id: int, db: Session = Depends(get_db)):
    dr = db.get(DryRunPlan, plan_id)
    if not dr:
        raise HTTPException(404, "Plan not found")
    return dr.impact_json