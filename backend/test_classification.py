import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cls.db")

from db.session import init_db
init_db()
from fastapi.testclient import TestClient
from main import app
from classification.engine import classify

client = TestClient(app)

def test_unknown():
    assert classify({"hostname": None, "vendor": None, "metadata": None})["category"] == "Unknown"

def test_router():
    assert classify({"hostname": "home-router", "vendor": None, "metadata": None})["category"] == "Router/Gateway"

def test_api():
    r = client.post("/api/devices", json={"ip_address": "10.0.0.1", "hostname": "my-printer"})
    did = r.json()["id"]
    r2 = client.get(f"/api/devices/{did}/classification")
    assert r2.json()["category"] == "Network Printer"
    r3 = client.get("/api/classifications")
    assert isinstance(r3.json(), list)