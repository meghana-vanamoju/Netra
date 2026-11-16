import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "policy.db")
from db.session import init_db
init_db()
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_plan_dryrun():
    # create audit
    r = client.post("/api/audits/run")
    aid = r.json()["audit_id"]
    r2 = client.post("/api/policies/plan", params={"audit_id": aid})
    assert r2.status_code == 200
    pids = r2.json()["policies"]
    if pids:
        r3 = client.post("/api/policies/dry-run", json=pids)
        assert r3.status_code == 200
        pid = r3.json()["plan_id"]
        assert client.get(f"/api/policies/dry-run/{pid}").status_code == 200
        assert client.get(f"/api/policies/dry-run/{pid}/impact").status_code == 200