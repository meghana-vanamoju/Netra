from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.session import get_db
from db.models import Device, DryRunPlan, AuditReport, Policy, PolicyExecution
from dns.providers.adguard import normalize_domain
from policy.engine import generate_policies, dry_run

router = APIRouter(prefix="/api/policies", tags=["policy"])


class PolicyConfigIn(BaseModel):
    name: str
    description: str = ""
    target_device_id: int | None = None
    enabled: bool = True
    blocked_domains: list[str] = []
    allowed_domains: list[str] = []


def _domains(values: list[str], label: str) -> list[str]:
    cleaned = []
    for value in values:
        domain = normalize_domain(value)
        if not domain:
            raise HTTPException(400, f"Invalid domain in {label}: {value}")
        if domain not in cleaned:
            cleaned.append(domain)
    return cleaned


def _config_from_payload(payload: PolicyConfigIn) -> dict:
    return {
        "description": payload.description.strip(),
        "target_device_id": payload.target_device_id,
        "enabled": payload.enabled,
        "blocked_domains": _domains(payload.blocked_domains, "blocked domains"),
        "allowed_domains": _domains(payload.allowed_domains, "allowed domains"),
        "internet_access_control": None,
        "dns_protection": "provider_user_rules",
        "schedule": None,
    }


def _policy_out(policy: Policy) -> dict:
    config = policy.config_json if isinstance(policy.config_json, dict) else {}
    return {
        "id": policy.id,
        "name": policy.name,
        "description": policy.description,
        "target": policy.target,
        "target_device_id": config.get("target_device_id"),
        "action": policy.action,
        "risk": policy.risk,
        "reversible": bool(policy.reversible),
        "status": policy.status,
        "config": {
            "enabled": bool(config.get("enabled", True)),
            "blocked_domains": config.get("blocked_domains", []),
            "allowed_domains": config.get("allowed_domains", []),
            "internet_access_control": config.get("internet_access_control"),
            "dns_protection": config.get("dns_protection"),
            "schedule": config.get("schedule"),
        },
    }


@router.post("/plan")
def plan(audit_id: int, db: Session = Depends(get_db)):
    rep = db.get(AuditReport, audit_id)
    if not rep:
        raise HTTPException(404, "Audit not found")
    policies = generate_policies(db, rep.findings_json or [])
    return {"policies": [p.id for p in policies]}


@router.post("")
def create_policy(payload: PolicyConfigIn, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name or len(name) > 128:
        raise HTTPException(400, "Policy name is required and must be at most 128 characters")
    if payload.target_device_id is not None and not db.get(Device, payload.target_device_id):
        raise HTTPException(404, "Target device was not found")
    config = _config_from_payload(payload)
    policy = Policy(
        name=name,
        description=config["description"],
        target=(
            str(payload.target_device_id)
            if payload.target_device_id is not None
            else None
        ),
        action="custom_dns_filter",
        risk="Low",
        reversible=1,
        status="proposed",
        config_json=config,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return _policy_out(policy)


@router.post("/preview")
def preview_policies(audit_id: int, db: Session = Depends(get_db)):
    """Return evidence-backed policy drafts without saving or applying them."""
    report = db.get(AuditReport, audit_id)
    if not report:
        raise HTTPException(404, "Audit not found")
    drafts = []
    for finding in report.findings_json or []:
        title = str(finding.get("title", "")).lower()
        if not any(word in title for word in ("tracking", "telemetry", "advertising")):
            continue
        drafts.append(
            {
                "name": "Block tracking domains",
                "action": "block_domain_category",
                "target_device_id": finding.get("device_id"),
                "risk": "Medium",
                "reason": finding.get("title"),
                "detection_rule": finding.get("detection_rule"),
                "evidence": finding.get("evidence", []),
                "recommended_next_step": finding.get("recommended_next_step"),
            }
        )
    return {"audit_id": audit_id, "drafts": drafts, "saved": False}


@router.get("")
def list_policies(db: Session = Depends(get_db)):
    return [_policy_out(policy) for policy in db.query(Policy).all()]


@router.get("/{policy_id}")
def get_policy(policy_id: int, db: Session = Depends(get_db)):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found")
    return _policy_out(policy)


@router.put("/{policy_id}")
def update_policy(
    policy_id: int, payload: PolicyConfigIn, db: Session = Depends(get_db)
):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found")
    if policy.status in {"applying", "applied"}:
        raise HTTPException(409, "Roll back an applied policy before editing it")
    name = payload.name.strip()
    if not name or len(name) > 128:
        raise HTTPException(400, "Policy name is required and must be at most 128 characters")
    if payload.target_device_id is not None and not db.get(Device, payload.target_device_id):
        raise HTTPException(404, "Target device was not found")
    config = _config_from_payload(payload)
    policy.name = name
    policy.description = config["description"]
    policy.target = (
        str(payload.target_device_id)
        if payload.target_device_id is not None
        else None
    )
    policy.config_json = config
    db.commit()
    db.refresh(policy)
    return _policy_out(policy)


@router.delete("/{policy_id}")
def delete_policy(policy_id: int, confirm: bool = False, db: Session = Depends(get_db)):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found")
    if not confirm:
        raise HTTPException(400, "Explicit confirmation required")
    if policy.status in {"applying", "applied"}:
        raise HTTPException(409, "Roll back an applied policy before deleting it")
    db.query(PolicyExecution).filter(PolicyExecution.policy_id == policy_id).delete()
    db.delete(policy)
    db.commit()
    return {"status": "deleted", "policy_id": policy_id}


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
