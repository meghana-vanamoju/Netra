import hashlib
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.models import ConfigSnapshot, DryRunPlan, Policy, PolicyExecution
from db.session import get_db
from dns.providers.adguard import normalize_domain
from enforcement.adapter import DNSBackendAdapter

router = APIRouter(prefix="/api/policies", tags=["consent"])

VALID_TRANSITIONS = {
    "proposed": {"dry-run completed"},
    "dry-run completed": {"awaiting approval", "approved"},
    "awaiting approval": {"approved"},
    "approved": {"applying"},
    "applying": {"applied", "failed"},
    "applied": {"reverted"},
}


def transition(policy, new_status):
    allowed = VALID_TRANSITIONS.get(policy.status, set())
    if new_status not in allowed:
        raise HTTPException(400, f"Invalid transition {policy.status} -> {new_status}")
    policy.status = new_status


@router.post("/{policy_id}/approve")
def approve(
    policy_id: int,
    plan_id: int,
    approver: str = "local-user",
    confirm: bool = False,
    db: Session = Depends(get_db),
):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found")
    plan = db.get(DryRunPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Dry-run plan not found")
    if not confirm:
        raise HTTPException(400, "Explicit confirmation required")
    policy.dry_run_plan_id = plan_id
    policy.approver = approver
    policy.approved_at = datetime.utcnow()
    transition(policy, "approved")
    db.commit()
    return {"status": "approved", "policy_id": policy_id}


@router.get("/{policy_id}/approval")
def approval(policy_id: int, db: Session = Depends(get_db)):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found")
    return {
        "status": policy.status,
        "approver": policy.approver,
        "approved_at": policy.approved_at,
        "plan_id": policy.dry_run_plan_id,
    }


def _policy_targets(policy, db):
    """Resolve the exact domains a consented policy may affect."""
    domains = []
    if policy.dry_run_plan_id:
        plan = db.get(DryRunPlan, policy.dry_run_plan_id)
        if plan and isinstance(plan.plan_json, dict):
            for value in plan.plan_json.get("domains") or []:
                domain = normalize_domain(value)
                if domain and domain not in domains:
                    domains.append(domain)
    if policy.target is not None:
        domain = normalize_domain(str(policy.target))
        if domain and domain not in domains:
            domains.append(domain)
    return domains


@router.post("/{policy_id}/apply")
def apply(policy_id: int, db: Session = Depends(get_db)):
    """Apply a policy only after explicit approval, dry-run and opt-in config."""
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found")
    if policy.status != "approved":
        raise HTTPException(400, "Policy not approved")

    adapter = DNSBackendAdapter()
    if not adapter.available():
        db.add(
            PolicyExecution(
                policy_id=policy_id,
                status="failed",
                details={"error": "No DNS provider configured", "backend": None},
            )
        )
        db.commit()
        raise HTTPException(503, "DNS provider not configured")
    if not adapter.enabled:
        db.add(
            PolicyExecution(
                policy_id=policy_id,
                status="failed",
                details={
                    "error": "DNS enforcement is disabled",
                    "backend": adapter.backend,
                    "hint": "Set NETRA_DNS_ENFORCEMENT_ENABLED explicitly",
                },
            )
        )
        db.commit()
        raise HTTPException(503, "DNS enforcement is disabled")

    domains = _policy_targets(policy, db)
    if not domains:
        raise HTTPException(400, "Approved policy has no validated target domains")

    # Capture the provider's current user rules so rollback can restore them.
    state = {"domains": domains, "policy_id": policy_id, "user_rules": []}
    try:
        if hasattr(adapter.provider, "filtering_status"):
            state["user_rules"] = adapter.provider.filtering_status()["user_rules"]
    except Exception:
        state["user_rules"] = []
    snapshot = ConfigSnapshot(
        backend=adapter.backend or "unknown",
        state_json=state,
        checksum=hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest(),
        policy_id=policy_id,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    transition(policy, "applying")
    db.commit()
    result = adapter.apply_policy(domains)
    result["policy_id"] = policy_id
    result["consent"] = {
        "approver": policy.approver,
        "approved_at": policy.approved_at.isoformat() if policy.approved_at else None,
        "plan_id": policy.dry_run_plan_id,
    }
    result["snapshot_id"] = snapshot.id
    if result.get("status") == "applied":
        execution_status = "applied"
        transition(policy, "applied")
    else:
        execution_status = "failed"
        transition(policy, "failed")
    db.add(PolicyExecution(policy_id=policy_id, status=execution_status, details=result))
    db.commit()
    if execution_status == "failed":
        raise HTTPException(503, result)
    return result


@router.get("/{policy_id}/execution")
def execution(policy_id: int, db: Session = Depends(get_db)):
    record = (
        db.query(PolicyExecution)
        .filter(PolicyExecution.policy_id == policy_id)
        .order_by(PolicyExecution.created_at.desc())
        .first()
    )
    if not record:
        raise HTTPException(404, "No execution record")
    return {"status": record.status, "details": record.details}


@router.get("/{policy_id}/rollback-status")
def rollback_status(policy_id: int, db: Session = Depends(get_db)):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found")
    return {
        "policy_id": policy_id,
        "status": policy.status,
        "rollback_ready": policy.status in ("applied", "failed"),
    }
