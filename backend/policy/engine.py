from db.models import Policy, DryRunPlan

ESSENTIAL = {"google.com", "microsoft.com", "apple.com"}

def generate_policies(db, audit_findings):
    policies = []
    for f in audit_findings:
        if "tracking" in f.get("title","").lower() or "telemetry" in f.get("title","").lower():
            p = Policy(name="Block tracking domains", description="Dry-run policy for tracking/telemetry domains",
                       target=f.get("device_id"), action="block_domain_category", risk="Medium", reversible=1, status="recommended")
            db.add(p)
            policies.append(p)
    db.commit()
    for p in policies:
        db.refresh(p)
    return policies

def dry_run(db, policy_ids):
    from db.models import Policy, DNSEvent
    policies = db.query(Policy).filter(Policy.id.in_(policy_ids)).all()
    affected_domains = []
    affected_queries = 0
    for p in policies:
        evs = db.query(DNSEvent).filter(DNSEvent.category.in_(["Advertising","Tracking/Analytics","Telemetry"])).all()
        for e in evs:
            if e.domain not in ESSENTIAL:
                affected_domains.append(e.domain)
                affected_queries += 1
    plan = {"policies": [p.id for p in policies], "affected_queries": affected_queries, "unique_domains": len(set(affected_domains))}
    impact = {"projected_blocked_queries": affected_queries, "note": "Projection based on recorded data"}
    dr = DryRunPlan(plan_json=plan, impact_json=impact)
    db.add(dr)
    db.commit()
    db.refresh(dr)
    return dr, plan, impact