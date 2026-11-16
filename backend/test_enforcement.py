import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "enf.db")
from db.session import init_db
init_db()
from fastapi.testclient import TestClient
from main import app
client = TestClient(app)
def test_status():
    r = client.get("/api/enforcement/status")
    assert r.status_code == 200
    assert r.json()["available"] is False
