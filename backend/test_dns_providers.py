from dns.providers.adguard import AdGuardHomeAdapter
from dns.providers.pihole import PiHoleAdapter
import pytest


def test_unavailable():
    assert AdGuardHomeAdapter().available() is False
    assert PiHoleAdapter().available() is False


def test_available():
    assert AdGuardHomeAdapter(url="http://x").available() is True
    assert PiHoleAdapter(url="http://x").available() is True


def test_adguard_collects_dhcp_and_static_leases(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "leases": [
                    {"ip": "192.168.88.10", "mac": "AA:BB", "hostname": "phone"}
                ],
                "static_leases": [{"ip": "192.168.88.11", "mac": "CC:DD"}],
            }

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr("dns.providers.adguard.httpx.get", fake_get)
    adapter = AdGuardHomeAdapter(
        url="http://192.168.88.1:3000/",
        username="netra-reader",
        password="secret",
    )

    devices = adapter.collect()

    assert calls[0][0] == "http://192.168.88.1:3000/control/dhcp/status"
    assert calls[0][1]["auth"] == ("netra-reader", "secret")
    assert [device["connection_type"] for device in devices] == ["dhcp", "static"]
    assert devices[0]["hostname"] == "phone"
    assert devices[1]["hostname"] is None
    assert all(device["online_status"] == "unknown" for device in devices)


def test_adguard_rejects_malformed_response_and_ignores_invalid_leases(monkeypatch):
    adapter = AdGuardHomeAdapter(url="http://192.168.88.1:3000")
    monkeypatch.setattr(adapter, "dhcp_status", lambda: [])
    with pytest.raises(ValueError, match="Invalid AdGuard Home DHCP response"):
        adapter.collect()

    monkeypatch.setattr(
        adapter,
        "dhcp_status",
        lambda: {
            "leases": [
                None,
                {"ip": "not-an-address"},
                {
                    "ip": "192.168.88.10",
                    "mac": 12,
                    "hostname": 7,
                    "expires": 99,
                },
            ],
            "static_leases": [],
        },
    )
    devices = adapter.collect()
    assert len(devices) == 1
    assert devices[0]["ip_address"] == "192.168.88.10"
    assert devices[0]["mac_address"] is None
    assert devices[0]["hostname"] is None
    assert devices[0]["lease_expires"] is None
