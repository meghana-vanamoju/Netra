import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "rd.db")
from db.session import init_db
init_db()
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_invalid_ip():
    r = client.post("/api/router/test", params={"ip":"999.999.999.999"})
    assert r.status_code == 400

def test_caps():
    r = client.get("/api/router/capabilities", params={"ip":"192.168.1.1"})
    assert r.status_code == 200
    assert "reachable" in r.json()