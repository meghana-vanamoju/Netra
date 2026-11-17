import os, tempfile
from unittest.mock import patch
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "rr.db")
from db.session import init_db
init_db()
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_arp_present_no_mgmt():
    with patch("discovery.router.adapter.arp_present", return_value=True):
        with patch("socket.create_connection", side_effect=OSError):
            r = client.get("/api/router/capabilities", params={"ip":"10.0.0.1"})
            assert r.status_code == 200
            j = r.json()
            assert j["network_reachable"] is True
            assert j["management_interface_available"] is False