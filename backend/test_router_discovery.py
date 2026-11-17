import os, tempfile
import httpx
import pytest
from unittest.mock import patch

os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "rd.db")
from db.session import init_db

init_db()
from fastapi.testclient import TestClient
from main import app


@pytest.fixture(autouse=True)
def authorize_test_network(monkeypatch):
    monkeypatch.setenv("NETRA_AUTHORIZED_CIDRS", "192.168.0.0/16")


client = TestClient(app)


def test_invalid_ip():
    r = client.post("/api/router/test", params={"ip": "999.999.999.999"})
    assert r.status_code == 400


def test_caps():
    r = client.get("/api/router/capabilities", params={"ip": "192.168.1.1"})
    assert r.status_code == 200
    assert "reachable" in r.json()


def test_router_inventory_reports_unsupported_without_adapter(monkeypatch):
    monkeypatch.delenv("NETRA_ADGUARD_API_URL", raising=False)
    r = client.post("/api/router/devices", params={"ip": "192.168.88.1"})
    assert r.status_code == 200
    assert r.json()["status"] == "unsupported"
    assert r.json()["devices"] == []


def test_router_inventory_persists_configured_adguard_leases(monkeypatch):
    monkeypatch.setenv("NETRA_ADGUARD_API_URL", "http://192.168.88.1:3000")
    monkeypatch.setenv("NETRA_ADGUARD_USERNAME", "reader")
    monkeypatch.setenv("NETRA_ADGUARD_PASSWORD", "not-returned")
    prior = client.post(
        "/api/devices",
        json={
            "ip_address": "192.168.88.19",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "hostname": "tablet",
        },
    ).json()
    lease = {
        "ip_address": "192.168.88.20",
        "mac_address": "aa:bb:cc:dd:ee:ff",
        "hostname": "tablet",
        "vendor": None,
        "connection_type": "dhcp",
        "online_status": "unknown",
        "lease_expires": None,
        "last_seen": None,
        "discovery_source": "router:adguard-home",
    }
    with patch(
        "dns.providers.adguard.AdGuardHomeAdapter.collect", return_value=[lease]
    ):
        response = client.post("/api/router/devices", params={"ip": "192.168.88.1"})

    assert response.status_code == 200
    assert response.json()["status"] == "available"
    assert "not-returned" not in response.text
    device = client.get("/api/devices", params={"ip": "192.168.88.20"}).json()[0]
    assert device["ip_address"] == "192.168.88.20"
    assert device["id"] == prior["id"]
    assert device["first_seen"] == prior["first_seen"]
    assert device["mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert device["metadata"]["connection_type"] == "dhcp"
    assert "router:adguard-home" in device["metadata"]["sources"]
    results = client.get("/api/discovery/results").json()
    assert any(item["discovery_source"] == "router:adguard-home" for item in results)


def test_router_inventory_rejects_public_ip():
    r = client.post("/api/router/devices", params={"ip": "8.8.8.8"})
    assert r.status_code == 400


def test_router_rejects_private_ip_outside_active_or_authorized_network(monkeypatch):
    monkeypatch.delenv("NETRA_AUTHORIZED_CIDRS", raising=False)
    with patch(
        "discovery.service.get_local_network_info",
        return_value={"subnet": "192.168.88.0/24"},
    ):
        response = client.post("/api/router/devices", params={"ip": "10.0.0.1"})
    assert response.status_code == 400


def test_router_inventory_reports_authentication_required(monkeypatch):
    monkeypatch.setenv("NETRA_ADGUARD_API_URL", "http://192.168.88.1:3000")
    request = httpx.Request("GET", "http://192.168.88.1:3000/control/dhcp/status")
    response = httpx.Response(401, request=request)
    error = httpx.HTTPStatusError("Unauthorized", request=request, response=response)
    with patch("dns.providers.adguard.AdGuardHomeAdapter.collect", side_effect=error):
        result = client.post("/api/router/devices", params={"ip": "192.168.88.1"})
    assert result.json()["status"] == "authentication_required"
    assert result.json()["devices"] == []


def test_router_inventory_reports_timeout_without_fake_devices(monkeypatch):
    monkeypatch.setenv("NETRA_ADGUARD_API_URL", "http://192.168.88.1:3000")
    with patch(
        "dns.providers.adguard.AdGuardHomeAdapter.collect",
        side_effect=httpx.TimeoutException("timed out"),
    ):
        result = client.post("/api/router/devices", params={"ip": "192.168.88.1"})
    assert result.json()["status"] == "timeout"
    assert result.json()["devices"] == []


def test_router_inventory_distinguishes_empty_from_unsupported(monkeypatch):
    monkeypatch.setenv("NETRA_ADGUARD_API_URL", "http://192.168.88.1:3000")
    with patch("dns.providers.adguard.AdGuardHomeAdapter.collect", return_value=[]):
        result = client.post("/api/router/devices", params={"ip": "192.168.88.1"})
    assert result.json()["status"] == "available"
    assert result.json()["devices"] == []
