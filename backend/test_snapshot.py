import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "snap.db")
from db.session import init_db
init_db()
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_create_verify():
    r = client.post("/api/snapshots", json={"backend":"none","state":{"a":1}})
    assert r.status_code == 200
    sid = r.json()["id"]
    r2 = client.get(f"/api/snapshots/{sid}")
    assert r2.json()["integrity_ok"] is True
    r3 = client.post(f"/api/snapshots/{sid}/rollback")
    assert r3.status_code == 503