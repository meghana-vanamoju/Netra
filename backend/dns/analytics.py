"""Domain classification, event ingestion and privacy metrics.

Category rules are evidence-based suffix matches. They are deliberately
conservative: an unmatched domain stays Unknown and is never described as
malicious. Confidence describes only the strength of the local rule match.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from dns.providers.adguard import normalize_domain

# suffix -> (category, evidence, confidence)
RULES = {
    "doubleclick.net": ("Advertising", "known advertising domain suffix", "high"),
    "googlesyndication.com": ("Advertising", "known advertising domain suffix", "high"),
    "adservice.google.com": ("Advertising", "known advertising domain suffix", "high"),
    "google-analytics.com": ("Tracking/Analytics", "known analytics domain suffix", "high"),
    "segment.io": ("Tracking/Analytics", "known analytics domain suffix", "high"),
    "mixpanel.com": ("Tracking/Analytics", "known analytics domain suffix", "medium"),
    "hotjar.com": ("Tracking/Analytics", "known analytics domain suffix", "medium"),
    "sentry.io": ("Telemetry", "known telemetry/error-reporting suffix", "high"),
    "telemetry.microsoft.com": ("Telemetry", "known telemetry suffix", "high"),
    "appinsights.visualstudio.com": ("Telemetry", "known telemetry suffix", "medium"),
    "facebook.com": ("Social media", "known social platform suffix", "high"),
    "instagram.com": ("Social media", "known social platform suffix", "high"),
    "linkedin.com": ("Social media", "known social platform suffix", "high"),
    "twitter.com": ("Social media", "known social platform suffix", "high"),
    "cdn.jsdelivr.net": ("Content delivery", "known CDN suffix", "high"),
    "akamaized.net": ("Content delivery", "known CDN suffix", "medium"),
    "cloudfront.net": ("Content delivery", "known CDN suffix", "medium"),
    "fastly.net": ("Content delivery", "known CDN suffix", "medium"),
    "microsoft.com": ("Essential services", "common first-party service suffix", "low"),
    "apple.com": ("Essential services", "common first-party service suffix", "low"),
    "google.com": ("Essential services", "common first-party service suffix", "low"),
}


def classify_domain_detailed(domain: str) -> dict:
    value = normalize_domain(domain)
    if not value:
        return {
            "domain": None,
            "category": "Unknown",
            "evidence": "invalid domain",
            "confidence": "none",
            "matched_rule": None,
        }
    # Longest suffix wins so specific rules beat broad first-party rules.
    for rule in sorted(RULES, key=len, reverse=True):
        if value == rule or value.endswith("." + rule):
            category, evidence, confidence = RULES[rule]
            return {
                "domain": value,
                "category": category,
                "evidence": f"{evidence} ({rule})",
                "confidence": confidence,
                "matched_rule": rule,
            }
    return {
        "domain": value,
        "category": "Unknown",
        "evidence": "no matching rule in the local category catalogue",
        "confidence": "none",
        "matched_rule": None,
    }


def classify_domain(domain: str) -> tuple[str, str]:
    """Backward-compatible two-value classification API."""
    result = classify_domain_detailed(domain)
    return result["category"], result["evidence"]


def _normalise_blocked(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int) and value in (0, 1):
        return value
    if isinstance(value, str):
        if value.lower() in {"1", "true", "blocked", "yes"}:
            return 1
        if value.lower() in {"0", "false", "allowed", "no"}:
            return 0
    return None


def ingest_events(db, records, source="manual", _retry=False):
    """Store normalized provider events with idempotent upsert semantics.

    Returns counts rather than raising on duplicate or malformed records so a
    provider sync can report exactly what happened.
    """
    from db.models import DNSEvent, Device

    inserted, duplicates, skipped = 0, 0, 0
    first = None
    staged = []
    seen_in_batch = set()
    for record in records:
        if not isinstance(record, dict):
            skipped += 1
            continue
        domain = normalize_domain(record.get("domain"))
        if not domain:
            skipped += 1
            continue
        event_id = record.get("source_event_id")
        event_id = str(event_id) if event_id else None
        if source and event_id:
            key = (source, event_id)
            if key in seen_in_batch:
                duplicates += 1
                continue
            seen_in_batch.add(key)
            exists = (
                db.query(DNSEvent.id)
                .filter(DNSEvent.source == source, DNSEvent.source_event_id == event_id)
                .first()
            )
            if exists:
                duplicates += 1
                continue
        client = record.get("client")
        client = client.strip() if isinstance(client, str) and client.strip() else None
        client_name = record.get("client_name")
        client_name = client_name.strip() if isinstance(client_name, str) and client_name.strip() else None
        device = None
        if client:
            device = db.query(Device).filter(Device.ip_address == client).first()
        if device is None and client_name:
            device = db.query(Device).filter(Device.hostname == client_name).first()
        timestamp = record.get("timestamp")
        if not isinstance(timestamp, datetime):
            timestamp = datetime.utcnow()
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        detail = classify_domain_detailed(domain)
        rules = record.get("rules")
        staged.append(
            DNSEvent(
                domain=domain,
                query_timestamp=timestamp,
                query_type=record.get("query_type"),
                device_id=device.id if device else None,
                category=detail["category"],
                blocked=_normalise_blocked(record.get("blocked")),
                source=source,
                source_event_id=event_id,
                client=client,
                client_name=client_name,
                reason=record.get("reason"),
                rules_json=rules if isinstance(rules, list) else None,
                upstream=record.get("upstream"),
                confidence=detail["confidence"],
            )
        )
    try:
        for event in staged:
            db.add(event)
        db.commit()
        inserted = len(staged)
        if staged:
            first = staged[0]
    except Exception:
        db.rollback()
        if _retry:
            return {"inserted": 0, "duplicates": 0, "skipped": len(records), "first": None}
        # Fall back to one-at-a-time inserts so a single bad row cannot lose the
        # rest of a provider sync.
        for record in records:
            try:
                result = ingest_events(db, [record], source=source, _retry=True)
                inserted += result["inserted"]
                duplicates += result["duplicates"]
                skipped += result["skipped"]
                if first is None and result["first"] is not None:
                    first = result["first"]
            except Exception:
                db.rollback()
                skipped += 1
    return {
        "inserted": inserted,
        "duplicates": duplicates,
        "skipped": skipped,
        "first": first,
    }


def ingest_event(db, payload):
    """Legacy single-event API used by POST /api/dns/events."""
    result = ingest_events(
        db,
        [
            {
                "domain": payload.get("domain"),
                "query_type": payload.get("query_type"),
                "client": payload.get("source_ip"),
                "blocked": payload.get("blocked"),
                "timestamp": payload.get("timestamp"),
            }
        ],
        source=payload.get("source") or "manual",
    )
    return result["first"]


def summary(db, device_id=None, since=None):
    """Privacy metrics over stored events.

    Missing blocked information is reported separately from an explicit
    allowed/blocked value; percentages use only events with known status.
    """
    from db.models import DNSEvent

    query = db.query(DNSEvent)
    if device_id:
        query = query.filter(DNSEvent.device_id == device_id)
    if isinstance(since, datetime):
        if since.tzinfo is not None:
            since = since.astimezone(timezone.utc).replace(tzinfo=None)
        query = query.filter(DNSEvent.query_timestamp >= since)
    events = query.all()
    total = len(events)
    domains = Counter(event.domain for event in events if event.domain)
    by_cat = Counter(event.category or "Unknown" for event in events)
    blocked = sum(1 for event in events if event.blocked == 1)
    allowed = sum(1 for event in events if event.blocked == 0)
    known = blocked + allowed
    blocked_domains = Counter(
        event.domain for event in events if event.blocked == 1 and event.domain
    )
    by_client = Counter(event.client or "unknown" for event in events)
    by_source = Counter(event.source or "manual" for event in events)
    hourly = defaultdict(int)
    for event in events:
        if event.query_timestamp:
            bucket = event.query_timestamp.replace(minute=0, second=0, microsecond=0)
            hourly[bucket.isoformat()] += 1
    evidence = {}
    for event in events:
        if event.category and event.category not in evidence:
            detail = classify_domain_detailed(event.domain or "")
            evidence[event.category] = {
                "evidence": detail["evidence"],
                "confidence": detail["confidence"],
            }
    return {
        "total": total,
        "unique_domains": len(domains),
        "by_category": dict(by_cat),
        "blocked": blocked,
        "allowed": allowed,
        "blocking_percentage": round(100 * blocked / known, 2) if known else None,
        "unknown_blocked_status": total - known,
        "top_domains": [
            {"domain": name, "count": count} for name, count in domains.most_common(10)
        ],
        "top_blocked_domains": [
            {"domain": name, "count": count}
            for name, count in blocked_domains.most_common(10)
        ],
        "by_client": [
            {"client": name, "count": count} for name, count in by_client.most_common(10)
        ],
        "by_source": dict(by_source),
        "timeline": [
            {"hour": hour, "count": hourly[hour]} for hour in sorted(hourly)
        ],
        "category_evidence": evidence,
    }
