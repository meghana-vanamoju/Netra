from datetime import datetime

from db.models import Policy
from dns.providers.adguard import normalize_domain

ESSENTIAL = {"google.com", "microsoft.com", "apple.com"}
POLICY_CATEGORIES = ("Advertising", "Tracking/Analytics", "Telemetry")


def _is_essential(domain):
    value = normalize_domain(domain)
    return bool(value and any(value == e or value.endswith("." + e) for e in ESSENTIAL))


def generate_policies(db, audit_findings):
    policies = []
    for finding in audit_findings:
        title = finding.get("title", "").lower()
        if "tracking" in title or "telemetry" in title or "advertising" in title:
            policy = Policy(
                name="Block tracking domains",
                description=(
                    "Dry-run policy for observed tracking/telemetry/advertising "
                    f"queries. Reason: {finding.get('title')} ({finding.get('detection_rule')})."
                ),
                target=finding.get("device_id"),
                action="block_domain_category",
                risk="Medium",
                reversible=1,
                status="proposed",
            )
            db.add(policy)
            policies.append(policy)
    db.commit()
    for policy in policies:
        db.refresh(policy)
    return policies


def dry_run(db, policy_ids):
    """Project policy impact from stored DNS events. No provider is modified."""
    from db.models import DNSEvent, Policy, DryRunPlan

    policies = db.query(Policy).filter(Policy.id.in_(policy_ids)).all()
    all_domains = []
    policy_details = []
    for policy in policies:
        query = db.query(DNSEvent).filter(DNSEvent.category.in_(POLICY_CATEGORIES))
        if policy.target is not None:
            query = query.filter(DNSEvent.device_id == policy.target)
        events = query.all()
        domains = sorted(
            {
                event.domain
                for event in events
                if event.domain and not _is_essential(event.domain)
            }
        )
        all_domains.extend(domains)
        policy_details.append(
            {
                "policy_id": policy.id,
                "name": policy.name,
                "action": policy.action,
                "target": policy.target,
                "device_id": policy.target,
                "affected_domains": domains,
                "affected_queries": len(
                    [
                        event
                        for event in events
                        if event.domain and not _is_essential(event.domain)
                    ]
                ),
                "reason": policy.description or "Observed category matches",
                "essential_exclusions": sorted(ESSENTIAL),
            }
        )
    unique_domains = sorted(set(all_domains))
    affected_queries = sum(item["affected_queries"] for item in policy_details)
    plan = {
        "policies": [policy.id for policy in policies],
        "affected_queries": affected_queries,
        "unique_domains": len(unique_domains),
        "domains": unique_domains,
        "policy_details": policy_details,
        "generated_at": datetime.utcnow().isoformat(),
        "mode": "dry-run",
    }
    impact = {
        "projected_blocked_queries": affected_queries,
        "note": "Projection based on stored DNS events, not a live provider change",
        "domains": unique_domains,
        "policy_details": [
            {
                "policy_id": item["policy_id"],
                "affected_queries": item["affected_queries"],
                "reason": item["reason"],
            }
            for item in policy_details
        ],
    }
    plan_record = DryRunPlan(plan_json=plan, impact_json=impact)
    db.add(plan_record)
    for policy in policies:
        if policy.status == "proposed":
            policy.status = "dry-run completed"
    db.commit()
    db.refresh(plan_record)
    return plan_record, plan, impact
