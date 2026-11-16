import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "cap.db")
from db.session import init_db
init_db()
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_cap():
    r = client.get("/api/backend/capabilities")
    assert r.status_code == 200
    assert "available" in r.json()