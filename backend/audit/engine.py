from datetime import datetime
import uuid

def run_audit(db, device_id=None):
    from db.models import Device, DNSEvent
    devices = [db.get(Device, device_id)] if device_id else db.query(Device).all()
    devices = [d for d in devices if d]
    findings = []
    for d in devices:
        dns = db.query(DNSEvent).filter(DNSEvent.device_id == d.id).all()
        if not d.hostname and not d.mac_address:
            findings.append(make_finding(d.id, "Missing identity", "Device has no hostname or MAC", "Medium", "incomplete metadata", ["hostname", "mac_address"]))
        if len(dns) > 100:
            findings.append(make_finding(d.id, "High DNS volume", f"{len(dns)} queries observed", "Low", "high query volume", [f"count={len(dns)}"]))
        track = [e for e in dns if e.category in ("Tracking/Analytics","Telemetry")]
        if len(track) >= 5:
            findings.append(make_finding(d.id, "Frequent tracking/telemetry", f"{len(track)} tracking/telemetry queries", "Medium", "tracking frequency", [f"count={len(track)}"]))
        unknown = [e for e in dns if e.category == "Unknown"]
        if len(unknown) >= 10:
            findings.append(make_finding(d.id, "Substantial unknown domains", f"{len(unknown)} unknown domain queries", "Low", "unknown domain volume", [f"count={len(unknown)}"]))
    if not devices:
        findings.append(make_finding(None, "Insufficient data", "No devices in inventory", "Informational", "no inventory", []))
    summary = {"devices": len(devices), "findings": len(findings)}
    return findings, summary

def make_finding(dev_id, title, desc, sev, rule, evidence):
    return {
        "id": str(uuid.uuid4()),
        "device_id": dev_id,
        "title": title,
        "description": desc,
        "severity": sev,
        "detection_rule": rule,
        "evidence": evidence,
        "timestamp": datetime.utcnow().isoformat(),
        "recommended_next_step": "Review device and consider policy planning (manual).",
    }