import hashlib
import json
from datetime import datetime, timezone

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


@router.post("/from-provider")
def snapshot_from_provider(db: Session = Depends(get_db)):
    """Capture the provider's current user rules without changing anything."""
    adapter = DNSBackendAdapter()
    if not adapter.available():
        raise HTTPException(503, "No DNS provider is configured")
    try:
        filtering = adapter.provider.filtering_status()
    except Exception:
        raise HTTPException(503, "Provider filtering state could not be captured") from None
    rules = filtering.get("user_rules")
    if not isinstance(rules, list):
        raise HTTPException(503, "Provider filtering state is incomplete")
    state = {
        "provider": adapter.backend,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "filtering_enabled": filtering.get("enabled"),
        "user_rules": rules,
        "filter_count": filtering.get("filter_count"),
    }
    raw = json.dumps(state, sort_keys=True)
    snapshot = ConfigSnapshot(
        backend=adapter.backend or "dns-provider",
        state_json=state,
        checksum=hashlib.sha256(raw.encode()).hexdigest(),
        policy_id=None,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return {
        "id": snapshot.id,
        "checksum": snapshot.checksum,
        "backend": snapshot.backend,
        "rules": len(rules),
        "type": "provider_configuration",
    }


@router.get("")
def list_snapshots(db: Session = Depends(get_db)):
    snapshots = db.query(ConfigSnapshot).all()
    return [
        {
            "id": item.id,
            "backend": item.backend,
            "created_at": item.created_at,
            "checksum": item.checksum,
            "type": (
                "local_state"
                if item.backend == "none"
                else "provider_configuration"
            ),
            "size_bytes": len(json.dumps(item.state_json or {}, sort_keys=True).encode()),
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
        "backend": snapshot.backend,
        "created_at": snapshot.created_at,
        "state": snapshot.state_json,
        "checksum": snapshot.checksum,
        "integrity_ok": integrity_ok,
        "type": "local_state" if snapshot.backend == "none" else "provider_configuration",
        "size_bytes": len(json.dumps(snapshot.state_json or {}, sort_keys=True).encode()),
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


@router.delete("/{snap_id}")
def delete_snapshot(snap_id: int, confirm: bool = False, db: Session = Depends(get_db)):
    snapshot = db.get(ConfigSnapshot, snap_id)
    if not snapshot:
        raise HTTPException(404, "Snapshot not found")
    if not confirm:
        raise HTTPException(400, "Explicit confirmation required")
    db.delete(snapshot)
    db.commit()
    return {"status": "deleted", "snapshot_id": snap_id}
