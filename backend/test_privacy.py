import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "priv.db")
from db.session import init_db
init_db()
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_score():
    r = client.get("/api/privacy/score")
    assert r.status_code == 200
    assert "score" in r.json()