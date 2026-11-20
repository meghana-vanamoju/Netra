import json
from types import SimpleNamespace

from network_enforcement import topology


MAC = "AA:BB:CC:DD:EE:24"


class FakeRunner:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        value = self.responses.get(tuple(argv))
        if value is None:
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="command not found",
            )
        return SimpleNamespace(returncode=0, stdout=value, stderr="")


def test_topology_separates_ethernet_uplink_and_wifi_hotspot(tmp_path):
    lease_file = tmp_path / "hotspot.leases"
    lease_file.write_text(
        f"0 {MAC} 10.42.0.24 phone *\n",
        encoding="utf-8",
    )
    responses = {
        (
            "nmcli",
            "--terse",
            "--escape",
            "no",
            "--fields",
            "DEVICE,TYPE,STATE,CONNECTION",
            "device",
            "status",
        ): "enp3s0f1:ethernet:100 (connected):Wired\n"
        "wlp2s0:wifi:100 (connected):Netra hotspot\n",
        (
            "nmcli",
            "--get-values",
            "802-11-wireless.mode",
            "connection",
            "show",
            "Netra hotspot",
        ): "ap\n",
        ("ip", "-j", "route", "show", "default"): json.dumps(
            [{"dst": "default", "dev": "enp3s0f1", "gateway": "192.168.88.1"}]
        ),
        ("ip", "-j", "-4", "addr", "show", "dev", "enp3s0f1"): json.dumps(
            [
                {
                    "addr_info": [
                        {
                            "family": "inet",
                            "scope": "global",
                            "local": "192.168.88.12",
                            "prefixlen": 24,
                        }
                    ]
                }
            ]
        ),
        ("ip", "-j", "-4", "addr", "show", "dev", "wlp2s0"): json.dumps(
            [
                {
                    "addr_info": [
                        {
                            "family": "inet",
                            "scope": "global",
                            "local": "10.42.0.1",
                            "prefixlen": 24,
                        }
                    ]
                }
            ]
        ),
        ("iw", "dev", "wlp2s0", "station", "dump"): f"Station {MAC} (on wlp2s0)\n",
        ("ip", "-j", "neigh", "show", "dev", "wlp2s0"): json.dumps(
            [
                {
                    "dst": "10.42.0.24",
                    "lladdr": MAC,
                    "state": ["REACHABLE"],
                    "dev": "wlp2s0",
                }
            ]
        ),
    }
    runner = FakeRunner(responses)

    result = topology.detect_network_topology(
        runner=runner,
        environ={"NETRA_DHCP_LEASE_FILES": str(lease_file)},
        now=1,
    )

    assert result["uplink"] == {
        "connected": True,
        "connection_type": "ethernet",
        "interface": "enp3s0f1",
        "ip_address": "192.168.88.12",
        "gateway": "192.168.88.1",
        "subnet": "192.168.88.0/24",
    }
    assert result["hotspot"]["active"] is True
    assert result["hotspot"]["interface"] == "wlp2s0"
    assert result["hotspot"]["subnet"] == "10.42.0.0/24"
    assert result["connected_device_count"] == 1
    assert result["clients"][0]["ip_address"] == "10.42.0.24"
    assert result["clients"][0]["identity_status"] == "validated"
    assert set(result["clients"][0]["sources"]) == {
        "wifi_station",
        "dhcp_lease",
        "neighbor_table",
    }


def test_neighbor_entry_alone_is_not_reported_as_connected():
    runner = FakeRunner(
        {
            ("iw", "dev", "wlp2s0", "station", "dump"): "",
            ("ip", "-j", "neigh", "show", "dev", "wlp2s0"): json.dumps(
                [
                    {
                        "dst": "10.42.0.24",
                        "lladdr": MAC,
                        "state": ["STALE"],
                        "dev": "wlp2s0",
                    }
                ]
            ),
        }
    )

    clients, warnings = topology.discover_hotspot_clients(
        "wlp2s0",
        runner=runner,
        environ={"NETRA_DHCP_LEASE_FILES": ""},
        now=1,
    )

    assert clients == []
    assert all("lease file" in warning.lower() for warning in warnings)


def test_conflicting_dhcp_and_neighbor_addresses_require_revalidation(tmp_path):
    lease_file = tmp_path / "hotspot.leases"
    lease_file.write_text(
        f"0 {MAC} 10.42.0.24 phone *\n",
        encoding="utf-8",
    )
    runner = FakeRunner(
        {
            ("iw", "dev", "wlp2s0", "station", "dump"): f"Station {MAC}\n",
            ("ip", "-j", "neigh", "show", "dev", "wlp2s0"): json.dumps(
                [
                    {
                        "dst": "10.42.0.25",
                        "lladdr": MAC,
                        "state": ["REACHABLE"],
                        "dev": "wlp2s0",
                    }
                ]
            ),
        }
    )

    clients, _ = topology.discover_hotspot_clients(
        "wlp2s0",
        runner=runner,
        environ={"NETRA_DHCP_LEASE_FILES": str(lease_file)},
        now=1,
    )

    assert clients[0]["ip_address"] is None
    assert clients[0]["identity_status"] == "conflict"
