import os, tempfile
import json
from types import SimpleNamespace

import pytest

os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "disc.db")

import api_discovery
import discovery.service as svc
from api_discovery import canonicalize_subnet
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


BROWSER_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
LAN_DEVICE = {
    "ip_address": "192.168.88.10",
    "mac_address": "AA:BB:CC:DD:EE:FF",
    "hostname": "office-phone",
    "discovery_source": "arp",
}


def _prepare_browser_scan(monkeypatch, subnet="192.168.88.0/24"):
    monkeypatch.setenv("NETRA_AUTHORIZED_CIDRS", subnet)
    monkeypatch.setattr(
        "discovery.service.get_local_network_info",
        lambda: {"subnet": subnet, "gateway": None, "ip_address": None},
    )
    monkeypatch.setattr(api_discovery, "_results", [])
    monkeypatch.setattr(api_discovery, "_router_results", [])


def test_canonicalize_subnet_handles_browser_encoding_layers():
    assert canonicalize_subnet("192.168.88.0/24") == "192.168.88.0/24"
    assert canonicalize_subnet("192.168.88.0%2F24") == "192.168.88.0/24"
    assert canonicalize_subnet("192.168.88.0%252F24") == "192.168.88.0/24"
    assert canonicalize_subnet(" 192.168.88.0%252F24 ") == "192.168.88.0/24"


@pytest.mark.parametrize("origin", BROWSER_ORIGINS)
@pytest.mark.parametrize(
    "query_value",
    ("192.168.88.0/24", "192.168.88.0%2F24", "192.168.88.0%252F24"),
)
def test_browser_lan_discovery_accepts_encoded_subnet(
    monkeypatch, origin, query_value
):
    """Regression: browser query encoding must not become a 400 on the route."""
    _prepare_browser_scan(monkeypatch)
    with patch(
        "api_discovery.discover_subnet", return_value=[dict(LAN_DEVICE)]
    ) as scan:
        response = client.post(
            f"/api/discovery/run?subnet={query_value}",
            headers={"Origin": origin, "Accept": "application/json"},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {"discovered": 1, "subnet": "192.168.88.0/24"}
    scan.assert_called_once_with("192.168.88.0/24")
    assert response.headers["access-control-allow-origin"] == origin

    # The frontend reads these two endpoints after a successful scan.
    assert client.get("/api/discovery/results").json()[0]["ip_address"] == (
        LAN_DEVICE["ip_address"]
    )
    inventory = client.get("/api/devices?limit=200").json()
    assert any(
        device["ip_address"] == LAN_DEVICE["ip_address"] for device in inventory
    )


@pytest.mark.parametrize("origin", BROWSER_ORIGINS)
@pytest.mark.parametrize(
    "subnet",
    (
        "10.10.0.0/16",
        "172.20.0.0/16",
        "192.168.0.0/16",
        "192.168.88.135/32",
    ),
)
def test_browser_lan_discovery_accepts_other_private_subnets(
    monkeypatch, origin, subnet
):
    _prepare_browser_scan(monkeypatch, subnet)
    device = dict(LAN_DEVICE, ip_address="10.1.1.5")
    with patch("api_discovery.discover_subnet", return_value=[device]) as scan:
        response = client.post(
            "/api/discovery/run",
            params={"subnet": subnet},
            headers={"Origin": origin, "Accept": "application/json"},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {"discovered": 1, "subnet": subnet}
    scan.assert_called_once_with(subnet)


@pytest.mark.parametrize("origin", BROWSER_ORIGINS)
@pytest.mark.parametrize(
    "query_value",
    (
        "8.8.8.0/24",
        "8.8.8.0%252F24",
        "127.0.0.0/24",
        "169.254.0.0/16",
        "224.0.0.0/24",
        "192.168.88.0",
        "192.168.88.0/33",
        "not-a-subnet",
        "192.168.88.0/24/8",
    ),
)
def test_browser_lan_discovery_rejects_unauthorized_subnets(
    monkeypatch, origin, query_value
):
    monkeypatch.delenv("NETRA_AUTHORIZED_CIDRS", raising=False)
    monkeypatch.setattr(
        "discovery.service.get_local_network_info",
        lambda: {"subnet": "192.168.88.0/24", "gateway": None, "ip_address": None},
    )
    monkeypatch.setattr(api_discovery, "_results", [])
    monkeypatch.setattr(api_discovery, "_router_results", [])
    with patch("api_discovery.discover_subnet") as scan:
        response = client.post(
            f"/api/discovery/run?subnet={query_value}",
            headers={"Origin": origin, "Accept": "application/json"},
        )

    assert response.status_code == 400, response.text
    assert response.headers["access-control-allow-origin"] == origin
    assert isinstance(response.json()["detail"], str)
    scan.assert_not_called()


PERSONAL_SUBNET = "192.168.29.0/24"
PERSONAL_DEVICE = {
    "ip_address": "192.168.29.10",
    "mac_address": "11:22:33:44:55:66",
    "hostname": "personal-laptop",
    "discovery_source": "arp",
}


@pytest.mark.parametrize("origin", BROWSER_ORIGINS)
@pytest.mark.parametrize(
    "query_value",
    ("192.168.29.0/24", "192.168.29.0%2F24", "192.168.29.0%252F24"),
)
def test_browser_lan_discovery_accepts_personal_subnet(
    monkeypatch, origin, query_value
):
    """The personal-router subnet must not regress the office-network fix."""
    _prepare_browser_scan(monkeypatch, PERSONAL_SUBNET)
    with patch(
        "api_discovery.discover_subnet", return_value=[dict(PERSONAL_DEVICE)]
    ) as scan:
        response = client.post(
            f"/api/discovery/run?subnet={query_value}",
            headers={"Origin": origin, "Accept": "application/json"},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {"discovered": 1, "subnet": PERSONAL_SUBNET}
    scan.assert_called_once_with(PERSONAL_SUBNET)
    assert response.headers["access-control-allow-origin"] == origin
    assert client.get("/api/discovery/results").json()[0]["ip_address"] == (
        PERSONAL_DEVICE["ip_address"]
    )
    inventory = client.get("/api/devices?limit=200").json()
    assert any(
        device["ip_address"] == PERSONAL_DEVICE["ip_address"] for device in inventory
    )


def test_personal_scan_preserves_other_subnet_inventory(monkeypatch):
    """Upserts refresh matching devices without deleting other-subnet records."""
    _prepare_browser_scan(monkeypatch, "192.168.88.0/24")
    with patch("api_discovery.discover_subnet", return_value=[dict(LAN_DEVICE)]):
        client.post(
            "/api/discovery/run", params={"subnet": "192.168.88.0/24"}
        )

    _prepare_browser_scan(monkeypatch, PERSONAL_SUBNET)
    with patch(
        "api_discovery.discover_subnet", return_value=[dict(PERSONAL_DEVICE)]
    ):
        response = client.post(
            "/api/discovery/run", params={"subnet": PERSONAL_SUBNET}
        )

    assert response.status_code == 200, response.text
    inventory_ips = {
        device["ip_address"]
        for device in client.get("/api/devices?limit=200").json()
    }
    assert LAN_DEVICE["ip_address"] in inventory_ips
    assert PERSONAL_DEVICE["ip_address"] in inventory_ips


def test_ipv6_loopback_origin_preflight_allowed():
    """Vite binds to ::1 on some hosts; that origin must reach the API."""
    response = client.options(
        "/api/discovery/run?subnet=192.168.29.0%2F24",
        headers={
            "Origin": "http://[::1]:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://[::1]:5173"
