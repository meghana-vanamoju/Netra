from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db
from db.models import AuditReport
from audit.engine import run_audit

router = APIRouter(prefix="/api/audits", tags=["audit"])
device_router = APIRouter(prefix="/api/devices", tags=["audit"])

@router.post("/run")
def run(
    scope: str = "network",
    device_id: int = None,
    subnet: str = None,
    db: Session = Depends(get_db),
):
    findings, summary = run_audit(
        db,
        device_id=device_id if scope == "device" else None,
        subnet=subnet if scope == "network" else None,
    )
    if subnet:
        summary = {**summary, "network_subnet": subnet}
    rep = AuditReport(
        scope=scope,
        device_id=device_id,
        network_subnet=subnet if scope == "network" else None,
        findings_json=findings,
        summary_json=summary,
    )
    db.add(rep)
    db.commit()
    db.refresh(rep)
    return {"audit_id": rep.id, "findings": len(findings), "summary": summary}

@router.get("")
def list_audits(subnet: str = None, db: Session = Depends(get_db)):
    query = db.query(AuditReport).order_by(AuditReport.created_at.desc())
    if subnet:
        query = query.filter(AuditReport.network_subnet == subnet.strip())
    reps = query.all()
    return [
        {
            "id": r.id,
            "scope": r.scope,
            "device_id": r.device_id,
            "network_subnet": r.network_subnet,
            "created_at": r.created_at,
        }
        for r in reps
    ]

@router.get("/{audit_id}")
def get_audit(audit_id: int, db: Session = Depends(get_db)):
    r = db.get(AuditReport, audit_id)
    if not r:
        raise HTTPException(404, "Audit not found")
    return {"id": r.id, "scope": r.scope, "summary": r.summary_json, "findings_count": len(r.findings_json or [])}

@router.get("/{audit_id}/findings")
def findings(audit_id: int, db: Session = Depends(get_db)):
    r = db.get(AuditReport, audit_id)
    if not r:
        raise HTTPException(404, "Audit not found")
    return r.findings_json or []

@device_router.get("/{device_id}/audit")
def device_audit(device_id: int, db: Session = Depends(get_db)):
    findings, summary = run_audit(db, device_id=device_id)
    return {"device_id": device_id, "findings": findings, "summary": summary}