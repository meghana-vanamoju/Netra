from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.models import Policy, PolicyExecution
from db.session import get_db
from dns.providers.adguard import normalize_domain
from enforcement.adapter import DNSBackendAdapter

router = APIRouter(prefix="/api/verification", tags=["verification"])


@router.get("/policy/{policy_id}")
def verify_policy(policy_id: int, db: Session = Depends(get_db)):
    """Verify a consented policy from real provider query-log evidence."""
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found")
    execution = (
        db.query(PolicyExecution)
        .filter(PolicyExecution.policy_id == policy_id)
        .order_by(PolicyExecution.created_at.desc())
        .first()
    )
    details = execution.details if execution and isinstance(execution.details, dict) else {}
    domains = []
    for value in details.get("domains") or []:
        domain = normalize_domain(value)
        if domain and domain not in domains:
            domains.append(domain)
    if not domains:
        return {
            "policy_id": policy_id,
            "status": "not_verified",
            "reason": "No applied target domains available for verification",
        }
    adapter = DNSBackendAdapter()
    if not adapter.available():
        return {
            "policy_id": policy_id,
            "status": "not_verified",
            "reason": "No DNS provider configured",
        }
    result = adapter.verify(domains)
    result["policy_id"] = policy_id
    result["policy_status"] = policy.status
    return result
