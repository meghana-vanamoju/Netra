"""Tests for the dashboard, host telemetry, policy CRUD and backup surfaces."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _provider_adapter(backend="adguard"):
    adapter = MagicMock()
    adapter.available.return_value = True
    adapter.enabled = True
    adapter.backend = backend
    return adapter


def test_bandwidth_endpoints_use_real_counter_deltas():
    before = {
        "eth0": {"rx_bytes": 1000, "tx_bytes": 500, "rx_packets": 10, "tx_packets": 5},
        "lo": {"rx_bytes": 10, "tx_bytes": 10, "rx_packets": 1, "tx_packets": 1},
    }
    after = {
        "eth0": {"rx_bytes": 3000, "tx_bytes": 900, "rx_packets": 14, "tx_packets": 7},
        "lo": {"rx_bytes": 10, "tx_bytes": 10, "rx_packets": 1, "tx_packets": 1},
    }

    with (
        patch("api_bandwidth._counters", side_effect=[before, after]),
        patch("api_bandwidth.time.sleep"),
        patch("discovery.service.get_local_network_info", return_value={"interface": "eth0"}),
    ):
        response = client.post("/api/bandwidth/sample", params={"interface": "eth0", "interval_ms": 1000})

    assert response.status_code == 200
    body = response.json()
    assert body["interface"] == "eth0"
    assert body["rx_bytes_delta"] == 2000
    assert body["tx_bytes_delta"] == 400
    assert body["rx_bytes_per_second"] == 2000
    assert body["scope"] == "netra-host-interface"

    with (
        patch("api_bandwidth._counters", return_value=after),
        patch("discovery.service.get_local_network_info", return_value={"interface": "eth0"}),
    ):
        history = client.get("/api/bandwidth/history", params={"interface": "eth0"})
    assert history.status_code == 200
    assert history.json()["returned"] >= 1


def test_adguard_diagnostics_marks_router_verification_as_false():
    with (
        patch(
            "api_diagnostics.provider_status",
            return_value={
                "state": "healthy",
                "provider": "adguard-home",
                "version": "v0.107.0",
                "authentication": "verified",
                "capabilities": ["api_connectivity", "filtering"],
                "unsupported": [],
            },
        ),
        patch(
            "api_diagnostics.provider_filtering",
            return_value={"enabled": True, "user_rules": ["||ads.example^"], "filter_count": 2},
        ),
        patch("api_diagnostics.provider_statistics", return_value={"total_queries": 4}),
        patch(
            "api_diagnostics.get_local_network_info",
            return_value={"interface": "eth0", "ip_address": "10.0.0.2", "gateway": "10.0.0.1", "subnet": "10.0.0.0/24"},
        ),
    ):
        response = client.get("/api/diagnostics/adguard")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"]["configured"] is True
    assert body["provider"]["authentication"] == "verified"
    assert body["filtering"]["available"] is True
    assert body["query_log"]["recorded_events"] >= 0
    assert body["router"]["dhcp_dns_verified"] is False
    assert body["scope"]["router_wide_protection_verified"] is False


def test_dashboard_summary_returns_provider_and_host_telemetry_without_router_claims():
    with (
        patch("api_dashboard.provider_status", return_value={"state": "healthy", "provider": "adguard-home", "message": "ok"}),
        patch("api_dashboard.discovery_status", return_value={"scanned": False, "subnet": None}),
        patch(
            "api_dashboard.enforcement_readiness",
            return_value={
                "provider_ready": True,
                "network_wide_ready": False,
                "provider_state": "healthy",
                "snapshot_count": 0,
            },
        ),
        patch(
            "api_dashboard.bandwidth_status",
            return_value={
                "interface": "eth0",
                "scope": "netra-host-interface",
                "latest": {"rx_bytes_per_second": 12.0, "tx_bytes_per_second": 5.0},
                "cumulative": {"rx_bytes": 100, "tx_bytes": 50},
                "sample_count": 1,
            },
        ),
    ):
        response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"]["state"] == "healthy"
    assert body["enforcement"]["network_wide_ready"] is False
    assert body["bandwidth"]["scope"] == "netra-host-interface"
    assert body["dns"]["available"] is True


def test_policy_crud_validates_domains_and_requires_delete_confirmation():
    response = client.post(
        "/api/policies",
        json={
            "name": "Phone tracker block",
            "description": "Evidence-backed test policy",
            "target_device_id": None,
            "enabled": True,
            "blocked_domains": ["TRACKER.Example."],
            "allowed_domains": ["needed.example"],
        },
    )
    assert response.status_code == 200
    policy = response.json()
    policy_id = policy["id"]
    assert policy["config"]["blocked_domains"] == ["tracker.example"]
    assert policy["config"]["enabled"] is True

    updated = client.put(
        f"/api/policies/{policy_id}",
        json={
            "name": "Phone tracker block v2",
            "description": "Updated rationale",
            "target_device_id": None,
            "enabled": False,
            "blocked_domains": ["tracker.example"],
            "allowed_domains": [],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["config"]["enabled"] is False

    listed = client.get("/api/policies")
    assert any(item["id"] == policy_id for item in listed.json())

    unconfirmed = client.delete(f"/api/policies/{policy_id}")
    assert unconfirmed.status_code == 400

    deleted = client.delete(f"/api/policies/{policy_id}", params={"confirm": True})
    assert deleted.status_code == 200
    assert client.get(f"/api/policies/{policy_id}").status_code == 404


def test_snapshot_from_provider_captures_real_user_rules_and_delete_requires_confirmation():
    adapter = _provider_adapter()
    adapter.provider.filtering_status.return_value = {
        "enabled": True,
        "user_rules": ["||ads.example^", "@@||needed.example^"],
        "filter_count": 2,
    }
    with patch("api_snapshot.DNSBackendAdapter", return_value=adapter):
        response = client.post("/api/snapshots/from-provider")

    assert response.status_code == 200
    snapshot_id = response.json()["id"]
    assert response.json()["rules"] == 2
    assert response.json()["type"] == "provider_configuration"

    detail = client.get(f"/api/snapshots/{snapshot_id}")
    assert detail.status_code == 200
    assert detail.json()["integrity_ok"] is True
    assert detail.json()["state"]["user_rules"] == ["||ads.example^", "@@||needed.example^"]

    assert client.delete(f"/api/snapshots/{snapshot_id}").status_code == 400
    assert client.delete(f"/api/snapshots/{snapshot_id}", params={"confirm": True}).status_code == 200


def test_dns_allow_rule_passes_action_to_provider():
    adapter = _provider_adapter()
    adapter.provider.filtering_status.return_value = {
        "enabled": True,
        "user_rules": [],
        "filter_count": 1,
    }
    adapter.provider.add_user_rule.return_value = {
        "provider": "adguard-home",
        "domain": "needed.example",
        "rule": "@@||needed.example^",
        "status": "applied",
    }
    with patch("enforcement.adapter.DNSBackendAdapter", return_value=adapter):
        response = client.post(
            "/api/dns/providers/filtering/rules",
            json={"domain": "needed.example", "action": "allow", "confirm": True},
        )

    assert response.status_code == 200
    adapter.provider.add_user_rule.assert_called_once_with("needed.example", action="allow")
