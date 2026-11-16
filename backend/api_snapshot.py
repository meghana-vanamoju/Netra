import hashlib, json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db
from db.models import ConfigSnapshot

router = APIRouter(prefix="/api/snapshots", tags=["snapshot"])

@router.post("")
def create_snapshot(backend: str = "none", state: dict = None, policy_id: int = None, db: Session = Depends(get_db)):
    state = state or {}
    raw = json.dumps(state, sort_keys=True)
    checksum = hashlib.sha256(raw.encode()).hexdigest()
    snap = ConfigSnapshot(backend=backend, state_json=state, checksum=checksum, policy_id=policy_id)
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return {"id": snap.id, "checksum": checksum}

@router.get("")
def list_snapshots(db: Session = Depends(get_db)):
    snaps = db.query(ConfigSnapshot).all()
    return [{"id": s.id, "backend": s.backend, "created_at": s.created_at, "checksum": s.checksum} for s in snaps]

@router.get("/{snap_id}")
def get_snapshot(snap_id: int, db: Session = Depends(get_db)):
    s = db.get(ConfigSnapshot, snap_id)
    if not s:
        raise HTTPException(404, "Snapshot not found")
    # verify
    raw = json.dumps(s.state_json or {}, sort_keys=True)
    ok = hashlib.sha256(raw.encode()).hexdigest() == s.checksum
    return {"id": s.id, "state": s.state_json, "checksum": s.checksum, "integrity_ok": ok}

@router.post("/{snap_id}/rollback")
def rollback(snap_id: int, db: Session = Depends(get_db)):
    s = db.get(ConfigSnapshot, snap_id)
    if not s:
        raise HTTPException(404, "Snapshot not found")
    backend = s.backend
    if backend == "none":
        raise HTTPException(503, "No backend configured")
    return {"status": "not_implemented", "snapshot_id": snap_id}