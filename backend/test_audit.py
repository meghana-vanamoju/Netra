import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "audit.db")
from db.session import init_db
init_db()
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_run_audit():
    r = client.post("/api/audits/run")
    assert r.status_code == 200
    aid = r.json()["audit_id"]
    r2 = client.get(f"/api/audits/{aid}/findings")
    assert isinstance(r2.json(), list)
    r3 = client.get("/api/audits")
    assert len(r3.json()) >= 1

def test_device_audit():
    r = client.post("/api/devices", json={"ip_address":"10.0.0.7","hostname":"unknownbox"})
    did = r.json()["id"]
    r2 = client.get(f"/api/devices/{did}/audit")
    assert "findings" in r2.json()