import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "dns.db")
from db.session import init_db
init_db()
from fastapi.testclient import TestClient
from main import app
from dns.analytics import classify_domain

client = TestClient(app)

def test_classify():
    assert classify_domain("ads.doubleclick.net")[0] == "Advertising"
    assert classify_domain("unknown.example")[0] == "Unknown"

def test_ingest_and_summary():
    r = client.post("/api/dns/events", json={"domain":"ads.doubleclick.net","source_ip":"10.0.0.5"})
    assert r.status_code == 200
    r2 = client.get("/api/dns/analytics/summary")
    assert r2.json()["total"] >= 1

def test_top_domains():
    r = client.get("/api/dns/analytics/domains")
    assert isinstance(r.json(), list)