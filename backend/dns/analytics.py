RULES = {
    "doubleclick.net": "Advertising",
    "googlesyndication.com": "Advertising",
    "google-analytics.com": "Tracking/Analytics",
    "segment.io": "Tracking/Analytics",
    "sentry.io": "Telemetry",
    "telemetry.microsoft.com": "Telemetry",
}

def classify_domain(domain: str) -> tuple[str, str]:
    d = domain.lower().strip().rstrip(".")
    # exact or suffix
    for rule, cat in RULES.items():
        if d == rule or d.endswith("." + rule):
            return cat, f"matched rule {rule}"
    return "Unknown", "no matching rule"

def ingest_event(db, payload):
    from db.models import DNSEvent, Device
    dev = None
    if payload.get("source_ip"):
        dev = db.query(Device).filter(Device.ip_address == payload["source_ip"]).first()
    ev = DNSEvent(
        domain=payload["domain"],
        query_type=payload.get("query_type"),
        device_id=dev.id if dev else None,
        category=classify_domain(payload["domain"])[0],
        blocked=payload.get("blocked"),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev

def summary(db, device_id=None, since=None):
    from db.models import DNSEvent
    q = db.query(DNSEvent)
    if device_id:
        q = q.filter(DNSEvent.device_id == device_id)
    events = q.all()
    total = len(events)
    domains = set(e.domain for e in events)
    by_cat = {}
    for e in events:
        by_cat[e.category] = by_cat.get(e.category, 0) + 1
    return {"total": total, "unique_domains": len(domains), "by_category": by_cat}