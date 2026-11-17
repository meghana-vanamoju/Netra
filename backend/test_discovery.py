import os, tempfile
import json
from types import SimpleNamespace

os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "disc.db")

import discovery.service as svc
from unittest.mock import patch
from fastapi.testclient import TestClient
from db.session import init_db
from main import app

init_db()
client = TestClient(app)


def test_private_validation():
    assert svc.is_private_subnet("192.168.1.0/24")
    assert not svc.is_private_subnet("8.8.8.0/24")


def test_run_mocked(monkeypatch):
    monkeypatch.setenv("NETRA_AUTHORIZED_CIDRS", "192.168.1.0/24")
    fake = [
        {
            "ip_address": "192.168.1.5",
            "mac_address": "AA:BB",
            "hostname": "h",
            "discovery_source": "arp",
        }
    ]
    with patch("api_discovery.discover_subnet", return_value=fake):
        r = client.post("/api/discovery/run", params={"subnet": "192.168.1.0/24"})
        assert r.status_code == 200
        assert r.json()["discovered"] == 1
    r2 = client.get("/api/discovery/results")
    assert len(r2.json()) == 1


def test_public_rejected():
    r = client.post("/api/discovery/run", params={"subnet": "8.8.8.0/24"})
    assert r.status_code == 400


def test_oversized_private_subnet_rejected():
    r = client.post("/api/discovery/run", params={"subnet": "10.0.0.0/8"})
    assert r.status_code == 400


def test_nonlocal_private_subnet_requires_explicit_authorization(monkeypatch):
    monkeypatch.delenv("NETRA_AUTHORIZED_CIDRS", raising=False)
    monkeypatch.setattr(
        "discovery.service.get_local_network_info",
        lambda: {"subnet": "192.168.88.0/24"},
    )
    response = client.post("/api/discovery/run", params={"subnet": "192.168.1.0/24"})
    assert response.status_code == 400
    assert "NETRA_AUTHORIZED_CIDRS" in response.json()["detail"]


def test_network_info_uses_active_default_route(monkeypatch):
    calls = [
        SimpleNamespace(
            stdout=json.dumps([{"dev": "wlp2s0", "gateway": "192.168.88.1"}])
        ),
        SimpleNamespace(
            stdout=json.dumps(
                [
                    {
                        "addr_info": [
                            {
                                "family": "inet",
                                "scope": "global",
                                "local": "192.168.88.135",
                                "prefixlen": 24,
                            }
                        ]
                    }
                ]
            )
        ),
    ]
    monkeypatch.setattr(
        "discovery.service.subprocess.run", lambda *args, **kwargs: calls.pop(0)
    )
    response = client.get("/api/discovery/network")
    assert response.status_code == 200
    assert response.json() == {
        "interface": "wlp2s0",
        "ip_address": "192.168.88.135",
        "gateway": "192.168.88.1",
        "subnet": "192.168.88.0/24",
    }


def test_discovery_cors_preflight():
    response = client.options(
        "/api/discovery/run?subnet=192.168.88.0%2F24",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_empty_scan_replaces_current_results(monkeypatch):
    import api_discovery

    monkeypatch.setenv("NETRA_AUTHORIZED_CIDRS", "192.168.1.0/24")
    api_discovery._router_results = []
    with patch(
        "api_discovery.discover_subnet",
        return_value=[
            {
                "ip_address": "192.168.1.8",
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "hostname": "phone",
                "discovery_source": "arp",
            }
        ],
    ):
        client.post("/api/discovery/run", params={"subnet": "192.168.1.0/24"})
    with patch("api_discovery.discover_subnet", return_value=[]):
        response = client.post(
            "/api/discovery/run", params={"subnet": "192.168.1.0/24"}
        )
    assert response.json()["discovered"] == 0
    assert client.get("/api/discovery/results").json() == []
