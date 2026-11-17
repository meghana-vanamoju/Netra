import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "sec.db")
from db.session import init_db
init_db()
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_invalid_dns():
    r = client.post("/api/dns/events", json={"domain":"notadomain"})
    assert r.status_code == 400

def test_unknown_device_audit():
    r = client.post("/api/audits/run")
    assert r.status_code == 200

def test_snapshot_integrity():
    r = client.post("/api/snapshots", json={"backend":"none","state":{"a":1}})
    sid = r.json()["id"]
    # tamper via DB not exposed; just verify endpoint
    r2 = client.get(f"/api/snapshots/{sid}")
    assert r2.json()["integrity_ok"] is True