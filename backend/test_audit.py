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

def test_audit_list_includes_and_filters_network_subnet():
    response = client.post(
        "/api/audits/run", params={"subnet": "192.168.1.0/24"}
    )
    assert response.status_code == 200
    assert response.json()["summary"]["network_subnet"] == "192.168.1.0/24"

    matching = client.get(
        "/api/audits", params={"subnet": "192.168.1.0/24"}
    ).json()
    assert any(item["network_subnet"] == "192.168.1.0/24" for item in matching)

    non_matching = client.get(
        "/api/audits", params={"subnet": "10.0.0.0/24"}
    ).json()
    assert all(item["network_subnet"] != "192.168.1.0/24" for item in non_matching)
