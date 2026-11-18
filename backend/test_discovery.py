import os
import tempfile
import json
import subprocess
import threading
from io import StringIO
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
    assert "NETRA_AUTHORIZED_CIDRS" in response.json()["detail"]["message"]
    assert response.json()["detail"]["code"] == "invalid_subnet"


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


def test_lan_results_do_not_include_router_inventory(monkeypatch):
    import api_discovery

    api_discovery._results_by_subnet = {
        "192.168.88.0/24": [
            {
                "ip_address": "192.168.88.10",
                "mac_address": "AA:BB",
                "discovery_source": "lan-discovery",
            }
        ]
    }
    api_discovery._router_results = [
        {
            "ip_address": "192.168.88.1",
            "mac_address": "CC:DD",
            "discovery_source": "router:adguard-home",
        }
    ]

    response = client.get(
        "/api/discovery/results", params={"subnet": "192.168.88.0/24"}
    )

    assert response.status_code == 200
    assert [item["ip_address"] for item in response.json()] == ["192.168.88.10"]


def test_router_inventory_is_not_in_lan_subnet_results(monkeypatch):
    import api_discovery

    api_discovery._results_by_subnet = {
        "192.168.88.0/24": [
            {
                "ip_address": "192.168.88.10",
                "mac_address": "AA:BB",
                "discovery_source": "lan-discovery",
            }
        ]
    }
    api_discovery._router_results = [
        {
            "ip_address": "192.168.88.1",
            "mac_address": "CC:DD",
            "discovery_source": "router:adguard-home",
        }
    ]

    response = client.get(
        "/api/discovery/results", params={"subnet": "192.168.88.0/24"}
    )

    assert all(item["discovery_source"].startswith("lan") for item in response.json())


def test_router_only_inventory_is_excluded_from_lan_results(monkeypatch):
    import api_discovery

    api_discovery._results_by_subnet = {"192.168.88.0/24": []}
    api_discovery._router_results = [
        {
            "ip_address": "192.168.88.1",
            "mac_address": "CC:DD",
            "discovery_source": "router:adguard-home",
        }
    ]

    response = client.get(
        "/api/discovery/results", params={"subnet": "192.168.88.0/24"}
    )

    assert response.status_code == 200
    assert response.json() == []


def test_two_subnets_keep_independent_current_snapshots(monkeypatch):
    import api_discovery

    api_discovery._results_by_subnet = {
        "192.168.88.0/24": [
            {
                "ip_address": "192.168.88.10",
                "mac_address": "AA:BB",
                "discovery_source": "lan-discovery",
            }
        ],
        "192.168.29.0/24": [
            {
                "ip_address": "192.168.29.10",
                "mac_address": "11:22",
                "discovery_source": "lan-discovery",
            }
        ],
    }

    office = client.get(
        "/api/discovery/results", params={"subnet": "192.168.88.0/24"}
    ).json()
    personal = client.get(
        "/api/discovery/results", params={"subnet": "192.168.29.0/24"}
    ).json()

    assert [item["ip_address"] for item in office] == ["192.168.88.10"]
    assert [item["ip_address"] for item in personal] == ["192.168.29.10"]


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
def test_browser_lan_discovery_accepts_encoded_subnet(monkeypatch, origin, query_value):
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
    assert response.json()["discovered"] == 1
    assert response.json()["subnet"] == "192.168.88.0/24"
    scan.assert_called_once()
    assert scan.call_args.args == ("192.168.88.0/24",)
    assert isinstance(scan.call_args.kwargs["metrics"], dict)
    assert response.json()["duration_seconds"] >= 0
    assert response.json()["probes_attempted"] == 0
    assert response.json()["hosts_responding"] == 0
    assert response.json()["partial_results"] is False
    assert response.headers["access-control-allow-origin"] == origin

    # The frontend reads these two endpoints after a successful scan.
    assert (
        client.get("/api/discovery/results").json()[0]["ip_address"]
        == (LAN_DEVICE["ip_address"])
    )
    inventory = client.get("/api/devices?limit=200").json()
    assert any(device["ip_address"] == LAN_DEVICE["ip_address"] for device in inventory)


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
    assert response.json()["discovered"] == 1
    assert response.json()["subnet"] == subnet
    scan.assert_called_once()
    assert scan.call_args.args == (subnet,)


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
    assert response.json()["detail"]["code"] == "invalid_subnet"
    assert isinstance(response.json()["detail"]["message"], str)
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
    assert response.json()["discovered"] == 1
    assert response.json()["subnet"] == PERSONAL_SUBNET
    scan.assert_called_once()
    assert scan.call_args.args == (PERSONAL_SUBNET,)
    assert response.headers["access-control-allow-origin"] == origin
    assert (
        client.get("/api/discovery/results").json()[0]["ip_address"]
        == (PERSONAL_DEVICE["ip_address"])
    )
    inventory = client.get("/api/devices?limit=200").json()
    assert any(
        device["ip_address"] == PERSONAL_DEVICE["ip_address"] for device in inventory
    )


def test_personal_scan_preserves_other_subnet_inventory(monkeypatch):
    """Upserts refresh matching devices without deleting other-subnet records."""
    _prepare_browser_scan(monkeypatch, "192.168.88.0/24")
    with patch("api_discovery.discover_subnet", return_value=[dict(LAN_DEVICE)]):
        client.post("/api/discovery/run", params={"subnet": "192.168.88.0/24"})

    _prepare_browser_scan(monkeypatch, PERSONAL_SUBNET)
    with patch("api_discovery.discover_subnet", return_value=[dict(PERSONAL_DEVICE)]):
        response = client.post("/api/discovery/run", params={"subnet": PERSONAL_SUBNET})

    assert response.status_code == 200, response.text
    inventory_ips = {
        device["ip_address"] for device in client.get("/api/devices?limit=200").json()
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


def _prepare_service_scan(monkeypatch, subnet="192.168.1.5/32"):
    monkeypatch.setenv("NETRA_AUTHORIZED_CIDRS", subnet)
    monkeypatch.setattr(
        svc,
        "get_local_network_info",
        lambda: {"subnet": None, "gateway": None, "ip_address": None},
    )
    monkeypatch.setattr(svc, "read_arp_table", lambda: [])


def test_read_neighbor_table_accepts_only_complete_valid_macs(monkeypatch):
    table = """IP address       HW type     Flags       HW address            Mask     Device
192.168.1.5      0x1        0x2         aa:bb:cc:dd:ee:ff     *        wlan0
192.168.1.6      0x1        0x0         11:22:33:44:55:66     *        wlan0
192.168.1.7      0x1        0x2         00:00:00:00:00:00     *        wlan0
192.168.1.8      0x1        0x2         invalid               *        wlan0
"""
    monkeypatch.setattr("builtins.open", lambda *args, **kwargs: StringIO(table))

    assert svc.read_arp_table() == [{"ip": "192.168.1.5", "mac": "AA:BB:CC:DD:EE:FF"}]


def test_discovery_uses_bounded_workers_and_caps_hosts(monkeypatch):
    _prepare_service_scan(monkeypatch, "192.168.0.0/16")
    active = 0
    peak_active = 0
    lock = threading.Lock()
    barrier = threading.Barrier(svc.MAX_PROBE_WORKERS)

    def fake_probe(ip, timeout):
        nonlocal active, peak_active
        with lock:
            active += 1
            peak_active = max(peak_active, active)
        barrier.wait(timeout=2)
        with lock:
            active -= 1
        return True, False, False

    monkeypatch.setattr(svc, "_probe_host", fake_probe)
    metrics = {}
    devices = svc.discover_subnet(
        "192.168.0.0/16",
        max_hosts=500,
        workers=500,
        overall_timeout=3,
        metrics=metrics,
    )

    assert peak_active == svc.MAX_PROBE_WORKERS
    assert len(devices) == svc.MAX_HOSTS_PER_SCAN
    assert metrics["probes_attempted"] == svc.MAX_HOSTS_PER_SCAN
    assert metrics["hosts_responding"] == svc.MAX_HOSTS_PER_SCAN


def test_host_timeout_is_counted_and_returns_partial_results(monkeypatch):
    _prepare_service_scan(monkeypatch)

    def time_out_probe(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(svc.subprocess, "run", time_out_probe)
    metrics = {}
    devices = svc.discover_subnet(
        "192.168.1.5/32", timeout=0.1, overall_timeout=1, metrics=metrics
    )

    assert devices == []
    assert metrics["timeout_count"] == 1
    assert metrics["partial_results"] is True


def test_ping_no_reply_exit_code_counts_as_timeout(monkeypatch):
    monkeypatch.setattr(
        svc.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )

    assert svc._probe_host("192.168.1.5", 1.0) == (False, True, False)


def test_overall_deadline_returns_partial_results(monkeypatch):
    _prepare_service_scan(monkeypatch)
    release_probe = threading.Event()

    def slow_probe(ip, timeout):
        release_probe.wait(timeout=2)
        return True, False, False

    monkeypatch.setattr(svc, "_probe_host", slow_probe)
    metrics = {}
    try:
        devices = svc.discover_subnet(
            "192.168.1.5/32", overall_timeout=0.1, metrics=metrics
        )
    finally:
        release_probe.set()

    assert devices == []
    assert metrics["probes_attempted"] == 1
    assert metrics["timeout_count"] == 1
    assert metrics["partial_results"] is True


def test_stale_neighbor_is_not_a_new_discovery(monkeypatch):
    _prepare_service_scan(monkeypatch)
    stale = {"ip": "192.168.1.5", "mac": "AA:BB:CC:DD:EE:FF"}
    monkeypatch.setattr(svc, "read_arp_table", lambda: [dict(stale)])
    monkeypatch.setattr(svc, "_probe_host", lambda *args: (False, False, False))

    assert svc.discover_subnet("192.168.1.5/32") == []


def test_new_neighbor_is_associated_and_hostname_remains_unknown(monkeypatch):
    _prepare_service_scan(monkeypatch)
    neighbor = {"ip": "192.168.1.5", "mac": "AA:BB:CC:DD:EE:FF"}
    observations = iter([[], [neighbor]])
    monkeypatch.setattr(svc, "read_arp_table", lambda: next(observations))
    monkeypatch.setattr(svc, "_probe_host", lambda *args: (False, False, False))
    monkeypatch.setattr(
        svc,
        "resolve_hostname",
        lambda *args: (_ for _ in ()).throw(AssertionError("unexpected lookup")),
    )

    devices = svc.discover_subnet("192.168.1.5/32")

    assert devices == [
        {
            "ip_address": "192.168.1.5",
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "hostname": None,
            "discovery_source": "arp",
        }
    ]


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.TimeoutExpired("getent", 0.01),
        FileNotFoundError("getent"),
    ],
)
def test_reverse_dns_timeout_and_failure_are_unknown(monkeypatch, failure):
    def fail_lookup(*args, **kwargs):
        raise failure

    monkeypatch.setattr(svc.subprocess, "run", fail_lookup)

    assert svc.resolve_hostname("192.168.1.5", timeout=0.01) is None


def test_probe_failure_returns_sanitized_structured_error(monkeypatch):
    _prepare_browser_scan(monkeypatch)
    with patch(
        "api_discovery.discover_subnet",
        side_effect=api_discovery.DiscoveryUnavailableError(
            "private subprocess details"
        ),
    ):
        response = client.post(
            "/api/discovery/run", params={"subnet": "192.168.88.0/24"}
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "probe_unavailable"
    assert response.json()["detail"]["message"] == (
        "LAN probes could not be started on this host."
    )
    assert response.json()["detail"]["partial_results"] is False
    assert "private subprocess details" not in response.text


def test_discovery_api_returns_scan_telemetry(monkeypatch):
    _prepare_browser_scan(monkeypatch)

    def fake_discover(subnet, *, metrics):
        metrics.update(
            probes_attempted=4,
            hosts_responding=2,
            timeout_count=1,
            probe_errors=0,
            partial_results=True,
        )
        return [dict(LAN_DEVICE)]

    with patch("api_discovery.discover_subnet", side_effect=fake_discover):
        response = client.post(
            "/api/discovery/run", params={"subnet": "192.168.88.0/24"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "discovered": 1,
        "subnet": "192.168.88.0/24",
        "scan_status": "partial",
        "duration_seconds": response.json()["duration_seconds"],
        "probes_attempted": 4,
        "hosts_responding": 2,
        "timeout_count": 1,
        "probe_errors": 0,
        "partial_results": True,
        "coverage": {
            "hosts_in_subnet": 0,
            "hosts_probed": 0,
            "coverage_complete": True,
            "unprobed_hosts": 0,
        },
        "last_scan_at": response.json()["last_scan_at"],
    }


def test_live_snapshot_replaces_previous_subnet_snapshot(monkeypatch):
    from db.session import get_session_factory
    from discovery.unified import replace_discovery_snapshot

    monkeypatch.setenv("NETRA_AUTHORIZED_CIDRS", "192.168.88.0/24")
    db = get_session_factory()()
    try:
        replace_discovery_snapshot(
            db,
            "192.168.88.0/24",
            [
                {
                    "ip_address": "192.168.88.10",
                    "mac_address": "AA:BB:CC:DD:EE:10",
                    "hostname": "first",
                    "discovery_source": "lan-discovery",
                }
            ],
        )
        replace_discovery_snapshot(
            db,
            "192.168.88.0/24",
            [
                {
                    "ip_address": "192.168.88.11",
                    "mac_address": "AA:BB:CC:DD:EE:11",
                    "hostname": "second",
                    "discovery_source": "lan-discovery",
                }
            ],
        )
    finally:
        db.close()

    live = client.get(
        "/api/devices", params={"live": "true", "subnet": "192.168.88.0/24"}
    )
    assert live.status_code == 200
    assert [item["ip_address"] for item in live.json()] == ["192.168.88.11"]


def test_partial_scan_keeps_unobserved_history_without_offline_claim(monkeypatch):
    from db.session import get_session_factory
    from discovery.unified import replace_discovery_snapshot

    monkeypatch.setenv("NETRA_AUTHORIZED_CIDRS", "192.168.88.0/24")
    db = get_session_factory()()
    try:
        replace_discovery_snapshot(
            db,
            "192.168.88.0/24",
            [
                {
                    "ip_address": "192.168.88.20",
                    "mac_address": "AA:BB:CC:DD:EE:20",
                    "hostname": "known",
                    "discovery_source": "lan-discovery",
                }
            ],
        )
        replace_discovery_snapshot(
            db,
            "192.168.88.0/24",
            [
                {
                    "ip_address": "192.168.88.21",
                    "mac_address": "AA:BB:CC:DD:EE:21",
                    "hostname": None,
                    "discovery_source": "lan-discovery",
                }
            ],
            scan_partial=True,
        )
    finally:
        db.close()

    historical = client.get("/api/devices", params={"subnet": "192.168.88.0/24"}).json()
    known = next(item for item in historical if item["ip_address"] == "192.168.88.20")
    assert known["is_current"] is True
    assert known["metadata"]["partial_scan_subnet"] == "192.168.88.0/24"
    assert known["metadata"]["scan_completeness"] == "partial"


def test_coverage_preserves_unprobed_current_device():
    from db.models import Device
    from db.session import get_session_factory
    from discovery.unified import replace_discovery_snapshot

    db = get_session_factory()()
    try:
        device = Device(
            ip_address="192.168.1.65",
            mac_address="AA:BB:CC:DD:EE:65",
            hostname="unprobed",
            discovery_source="lan-discovery",
            is_current=True,
            network_subnet="192.168.1.0/24",
        )
        db.add(device)
        db.commit()

        replace_discovery_snapshot(
            db,
            "192.168.1.0/24",
            [
                {
                    "ip_address": "192.168.1.10",
                    "mac_address": "AA:BB:CC:DD:EE:10",
                    "hostname": "probed",
                    "discovery_source": "lan-discovery",
                }
            ],
            scan_partial=False,
            probed_addresses={f"192.168.1.{i}" for i in range(1, 65)},
            coverage_complete=False,
        )
    finally:
        db.close()

    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    devices = client.get(
        "/api/devices", params={"subnet": "192.168.1.0/24"}
    ).json()
    unprobed = next(item for item in devices if item["ip_address"] == "192.168.1.65")
    assert unprobed["is_current"] is True
    assert unprobed["metadata"]["scan_completeness"] == "not_probed"
