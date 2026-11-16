import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "dev.db")

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_empty():
    r = client.get("/api/devices")
    assert r.status_code == 200
    assert r.json() == []

def test_register_and_get():
    r = client.post("/api/devices", json={"ip_address":"10.0.0.5","hostname":"phone"})
    assert r.status_code == 201
    did = r.json()["id"]
    r2 = client.get(f"/api/devices/{did}")
    assert r2.json()["hostname"] == "phone"

def test_upsert():
    client.post("/api/devices", json={"ip_address":"10.0.0.5","mac_address":"AA:BB:CC:DD:EE:FF","hostname":"phone2"})
    r = client.get("/api/devices?ip=10.0.0.5")
    assert len(r.json()) == 1

def test_not_found():
    assert client.get("/api/devices/99999").status_code == 404

def test_validation():
    assert client.post("/api/devices", json={}).status_code == 422

def test_filter():
    client.post("/api/devices", json={"ip_address":"10.0.0.9","vendor":"Acme"})
    r = client.get("/api/devices?vendor=Acme")
    assert any(d["vendor"]=="Acme" for d in r.json())