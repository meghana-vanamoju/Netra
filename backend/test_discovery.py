import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "disc.db")

import discovery.service as svc
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_private_validation():
    assert svc.is_private_subnet("192.168.1.0/24")
    assert not svc.is_private_subnet("8.8.8.0/24")

def test_run_mocked():
    fake = [{"ip_address":"192.168.1.5","mac_address":"AA:BB","hostname":"h","discovery_source":"arp"}]
    with patch("api_discovery.discover_subnet", return_value=fake):
        r = client.post("/api/discovery/run", params={"subnet":"192.168.1.0/24"})
        assert r.status_code == 200
        assert r.json()["discovered"] == 1
    r2 = client.get("/api/discovery/results")
    assert len(r2.json()) == 1

def test_public_rejected():
    r = client.post("/api/discovery/run", params={"subnet":"8.8.8.0/24"})
    assert r.status_code == 400