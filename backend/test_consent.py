import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "consent.db")
from db.session import init_db
init_db()
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_approve_requires_confirm():
    r = client.post("/api/audits/run")
    aid = r.json()["audit_id"]
    r2 = client.post("/api/policies/plan", params={"audit_id": aid})
    pids = r2.json()["policies"]
    if not pids:
        # create policy manually via plan none; skip
        return
    pid = pids[0]
    # create dry run
    r3 = client.post("/api/policies/dry-run", json=pids)
    plan_id = r3.json()["plan_id"]
    r4 = client.post(f"/api/policies/{pid}/approve", params={"plan_id": plan_id, "confirm": False})
    assert r4.status_code == 400
    r5 = client.post(f"/api/policies/{pid}/approve", params={"plan_id": plan_id, "confirm": True})
    assert r5.status_code == 200
    # apply without backend -> 503
    r6 = client.post(f"/api/policies/{pid}/apply")
    assert r6.status_code == 503