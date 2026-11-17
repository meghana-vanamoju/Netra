import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.models import ConfigSnapshot, Policy, PolicyExecution
from db.session import get_db
from enforcement.adapter import DNSBackendAdapter

router = APIRouter(prefix="/api/snapshots", tags=["snapshot"])


@router.post("")
def create_snapshot(
    backend: str = "none",
    state: dict = None,
    policy_id: int = None,
    db: Session = Depends(get_db),
):
    state = state or {}
    raw = json.dumps(state, sort_keys=True)
    checksum = hashlib.sha256(raw.encode()).hexdigest()
    snapshot = ConfigSnapshot(
        backend=backend, state_json=state, checksum=checksum, policy_id=policy_id
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return {"id": snapshot.id, "checksum": checksum}


@router.get("")
def list_snapshots(db: Session = Depends(get_db)):
    snapshots = db.query(ConfigSnapshot).all()
    return [
        {
            "id": item.id,
            "backend": item.backend,
            "created_at": item.created_at,
            "checksum": item.checksum,
        }
        for item in snapshots
    ]


@router.get("/{snap_id}")
def get_snapshot(snap_id: int, db: Session = Depends(get_db)):
    snapshot = db.get(ConfigSnapshot, snap_id)
    if not snapshot:
        raise HTTPException(404, "Snapshot not found")
    raw = json.dumps(snapshot.state_json or {}, sort_keys=True)
    integrity_ok = hashlib.sha256(raw.encode()).hexdigest() == snapshot.checksum
    return {
        "id": snapshot.id,
        "state": snapshot.state_json,
        "checksum": snapshot.checksum,
        "integrity_ok": integrity_ok,
    }


@router.post("/{snap_id}/rollback")
def rollback(snap_id: int, confirm: bool = False, db: Session = Depends(get_db)):
    snapshot = db.get(ConfigSnapshot, snap_id)
    if not snapshot:
        raise HTTPException(404, "Snapshot not found")
    if snapshot.backend == "none":
        raise HTTPException(503, "No backend configured")
    if not confirm:
        raise HTTPException(400, "Explicit confirmation required for rollback")
    adapter = DNSBackendAdapter()
    if not adapter.available() or not adapter.enabled:
        raise HTTPException(503, "DNS provider enforcement is not enabled")
    result = adapter.restore_state(snapshot.state_json or {})
    result["snapshot_id"] = snap_id
    if result.get("status") not in ("restored", "rolled_back"):
        raise HTTPException(503, result)
    if snapshot.policy_id:
        policy = db.get(Policy, snapshot.policy_id)
        if policy and policy.status == "applied":
            policy.status = "reverted"
        db.add(
            PolicyExecution(
                policy_id=snapshot.policy_id,
                status="rolled_back",
                details=result,
            )
        )
    db.commit()
    return result
