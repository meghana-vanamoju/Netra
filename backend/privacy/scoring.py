def privacy_score(events):
    track = sum(1 for e in events if e.get("category") in ("Tracking/Analytics","Telemetry"))
    unknown = sum(1 for e in events if e.get("category") == "Unknown")
    score = min(100, track*2 + unknown)
    return {"score": score, "tracking_events": track, "unknown_events": unknown, "explanation": "based on observed events"}