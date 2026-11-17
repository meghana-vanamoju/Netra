import time, statistics, json, os, sys
from datetime import datetime

def percentile(data, p):
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s)-1) * (p/100.0)
    f = int(k)
    c = f+1 if f+1 < len(s) else f
    if f == c:
        return s[f]
    return s[f] + (s[c]-s[f])*(k-f)

def measure(fn, iterations=10):
    times = []
    errors = 0
    for _ in range(iterations):
        start = time.perf_counter()
        try:
            fn()
        except Exception:
            errors += 1
        elapsed = (time.perf_counter()-start)*1000.0
        times.append(elapsed)
    return {
        "iterations": iterations,
        "total_ms": sum(times),
        "avg_ms": statistics.mean(times) if times else 0,
        "median_ms": statistics.median(times) if times else 0,
        "p95_ms": percentile(times,95),
        "errors": errors,
        "times_ms": times,
    }

def run_all(iterations=10, dataset=100):
    import tempfile, os as _os
    orig_env = _os.environ.get("NETRA_DB_PATH")
    p = os.path.join(tempfile.mkdtemp(), "bench.db")
    _os.environ["NETRA_DB_PATH"] = p
    import db.session as s
    orig_engine = s._engine
    orig_session = s._SessionLocal
    s._engine = None
    s._SessionLocal = None
    from db.session import init_db
    init_db()
    from db.session import get_session_factory
    db = get_session_factory()()
    from db.models import Device, DNSEvent
    # seed
    for i in range(dataset):
        db.add(Device(ip_address=f"10.0.0.{i%254+1}", hostname=f"dev{i}"))
    db.commit()
    for i in range(dataset*2):
        db.add(DNSEvent(domain="example.com", device_id=1))
    db.commit()

    results = {}
    # device retrieval
    def t1():
        db.query(Device).all()
    results["device_retrieval"] = measure(t1, iterations)

    # classification
    from classification.engine import classify
    dev = db.query(Device).first()
    def t2():
        classify(dev)
    results["classification"] = measure(t2, iterations)

    # dns aggregation
    def t3():
        db.query(DNSEvent).count()
    results["dns_aggregation"] = measure(t3, iterations)

    # audit
    from audit.engine import run_audit
    def t4():
        run_audit(db)
    results["audit_generation"] = measure(t4, iterations)

    db.close()
    import db.session as s
    s._engine = orig_engine
    s._SessionLocal = orig_session
    if orig_env is None:
        _os.environ.pop("NETRA_DB_PATH", None)
    else:
        _os.environ["NETRA_DB_PATH"] = orig_env
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "dataset_size": dataset,
        "iterations": iterations,
        "results": results,
    }
    return report

if __name__ == "__main__":
    iters = int(sys.argv[1]) if len(sys.argv)>1 else 10
    size = int(sys.argv[2]) if len(sys.argv)>2 else 100
    rep = run_all(iters, size)
    os.makedirs("benchmarks", exist_ok=True)
    with open("benchmarks/results.json","w") as f:
        json.dump(rep, f, indent=2)
    # markdown
    lines = ["# Netra Benchmark Results", "", f"Timestamp: {rep['timestamp']}", f"Dataset: {rep['dataset_size']}", ""]
    for k,v in rep["results"].items():
        lines.append(f"## {k}")
        lines.append(f"- avg_ms: {v['avg_ms']:.3f}")
        lines.append(f"- median_ms: {v['median_ms']:.3f}")
        lines.append(f"- p95_ms: {v['p95_ms']:.3f}")
        lines.append(f"- errors: {v['errors']}")
        lines.append("")
    with open("benchmarks/report.md","w") as f:
        f.write("\n".join(lines))
    print(json.dumps(rep, indent=2))
