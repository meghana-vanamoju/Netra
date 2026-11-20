import ipaddress

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api_network_control import (
    _active_device_rows,
    _enforcement_status,
    _network_context,
    require_loopback_client,
)
from db.models import Base, Device, DeviceNetworkControl, DeviceObservation
from network_enforcement.config import NetworkEnforcementConfig
from network_enforcement.constants import MODE_INTERNET_ACCESS
from network_enforcement.commands import CommandResult


MAC_A = "AA:BB:CC:DD:EE:24"
MAC_B = "AA:BB:CC:DD:EE:25"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def _client(mac, ip):
    return {
        "ip_address": ip,
        "mac_address": mac,
        "hostname": None,
        "connection_status": "connected",
        "identity_status": "validated",
        "sources": ["wifi_station", "dhcp_lease"],
    }


def _request(host):
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/devices/1/network-control/apply",
            "raw_path": b"/api/devices/1/network-control/apply",
            "query_string": b"",
            "headers": [],
            "client": (host, 54321),
            "server": ("127.0.0.1", 8084),
        }
    )


def test_network_control_mutations_require_loopback():
    with pytest.raises(HTTPException) as exc:
        require_loopback_client(_request("192.168.1.30"))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "loopback_required"

    assert require_loopback_client(_request("127.0.0.1")) is None


def _enabled_config(*, dry_run=False):
    return NetworkEnforcementConfig(
        enabled=True,
        dry_run=dry_run,
        table="netra",
        interface="wlp2s0",
        ifb=None,
        command_timeout_seconds=3,
        observation_ttl_seconds=300,
    )


def _hotspot_topology():
    return {"hotspot": {"active": True, "interface": "wlp2s0"}}


def _helper_result(status="available", authorized=True):
    return {
        "status": status,
        "authorized": authorized,
        "nftables_available": status == "available",
        "state": {"table": {"name": "netra"}, "chain": []},
        "error": None,
    }


def test_enforcement_readiness_distinguishes_helper_permission(monkeypatch):
    import api_network_control

    monkeypatch.setattr(
        api_network_control, "_effective_net_admin_status", lambda: "missing"
    )
    monkeypatch.setattr(
        api_network_control,
        "_helper_readiness",
        lambda config: _helper_result("permission_denied", False),
    )

    readiness = _enforcement_status(_hotspot_topology(), _enabled_config())

    assert readiness["privilege_model"] == "restricted_local_helper"
    assert readiness["backend_cap_net_admin"] == "missing"
    assert readiness["helper_status"] == "permission_denied"
    assert readiness["helper_authorized"] is False
    assert readiness["nftables_inspection_status"] == "permission_denied"
    assert readiness["apply_permitted"] is False
    assert readiness["physical_connectivity_confirmed"] is False


def test_enforcement_dry_run_checks_helper_access_for_restore(monkeypatch):
    import api_network_control

    monkeypatch.setattr(
        api_network_control, "_helper_readiness", lambda config: _helper_result()
    )

    readiness = _enforcement_status(_hotspot_topology(), _enabled_config(dry_run=True))

    assert readiness["status"] == "dry_run"
    assert readiness["mutation_permitted"] is True
    assert readiness["apply_permitted"] is False
    assert readiness["helper_authorized"] is True


def test_enforcement_readiness_does_not_require_backend_cap_net_admin(monkeypatch):
    import api_network_control

    monkeypatch.setattr(
        api_network_control, "_effective_net_admin_status", lambda: "missing"
    )
    monkeypatch.setattr(
        api_network_control,
        "_helper_readiness",
        lambda config: _helper_result(),
    )

    readiness = _enforcement_status(_hotspot_topology(), _enabled_config())

    assert readiness["backend_cap_net_admin"] == "missing"
    assert readiness["nftables_inspection_status"] == "available"
    assert readiness["nftables_write_permission_status"] == "helper_capability_not_write_probed"
    assert readiness["status"] == "ready"
    assert readiness["apply_permitted"] is True


def test_effective_net_admin_status_reads_only_effective_capabilities(tmp_path):
    import api_network_control

    status_file = tmp_path / "status"
    status_file.write_text("CapEff:\t0000000000001000\n", encoding="ascii")
    assert api_network_control._effective_net_admin_status(status_file) == "present"

    status_file.write_text("CapEff:\t0000000000000000\n", encoding="ascii")
    assert api_network_control._effective_net_admin_status(status_file) == "missing"


def test_apply_endpoint_rejects_remote_and_unconfirmed_requests(monkeypatch):
    import api_network_control
    from db.session import get_db
    from main import app

    def unused_db():
        yield None

    def network_must_not_be_inspected():
        raise AssertionError(
            "an unapproved request must not inspect or change networking"
        )

    monkeypatch.setattr(
        api_network_control, "detect_network_topology", network_must_not_be_inspected
    )
    app.dependency_overrides[get_db] = unused_db
    try:
        remote = TestClient(app, client=("192.0.2.15", 54321))
        denied = remote.post(
            "/api/devices/1/network-control/apply",
            json={
                "plan_id": 1,
                "action": "block_internet",
                "confirm": True,
                "approver": "tester",
            },
        )
        assert denied.status_code == 403
        assert denied.json()["detail"]["code"] == "loopback_required"

        local = TestClient(app, client=("127.0.0.1", 54321))
        unconfirmed = local.post(
            "/api/devices/1/network-control/apply",
            json={
                "plan_id": 1,
                "action": "block_internet",
                "confirm": False,
                "approver": "tester",
            },
        )
        assert unconfirmed.status_code == 400
        assert unconfirmed.json()["detail"]["code"] == "confirmation_required"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_http_plan_and_apply_keep_disabled_enforcement_non_mutating(
    db_session, monkeypatch
):
    import api_network_control
    import network_enforcement.commands as commands
    from db.session import get_db
    from main import app

    config = NetworkEnforcementConfig(
        enabled=False,
        dry_run=True,
        table="netra",
        interface=None,
        ifb=None,
        command_timeout_seconds=3,
        observation_ttl_seconds=300,
    )
    topology = {
        "hotspot": {
            "active": True,
            "interface": "wlp2s0",
            "subnet": "10.42.0.0/24",
        },
        "clients": [_client(MAC_A, "10.42.0.24")],
    }

    def unused_network_command(*args, **kwargs):
        raise AssertionError("disabled enforcement must not execute nft commands")

    def override_db():
        yield db_session

    monkeypatch.setattr(
        api_network_control, "detect_network_topology", lambda: topology
    )
    monkeypatch.setattr(NetworkEnforcementConfig, "from_env", lambda: config)
    monkeypatch.setattr(commands.subprocess, "run", unused_network_command)
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app, client=("127.0.0.1", 54321))
        planned = client.post(
            "/api/devices/1/network-control/plan",
            json={"action": "block_internet"},
        )
        assert planned.status_code == 200
        plan = planned.json()
        assert plan["plan"]["safety"]["modifies_host_firewall"] is False
        assert plan["plan"]["apply_allowed"] is False
        device_id = plan["plan"]["device"]["device_id"]

        rejected = client.post(
            f"/api/devices/{device_id}/network-control/apply",
            json={
                "plan_id": plan["plan_id"],
                "action": "block_internet",
                "confirm": True,
                "approver": "test",
            },
        )
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "apply_not_permitted"

        monkeypatch.setattr(
            api_network_control,
            "verify_internet_block",
            lambda *args, **kwargs: {
                "applied": False,
                "verified": True,
                "reasons": [],
            },
        )
        verified = client.post(f"/api/devices/{device_id}/network-control/verify")
        assert verified.status_code == 200
        assert verified.json()["internet_access"] == "allowed"
        assert verified.json()["verified"] is True

        history = client.get(f"/api/devices/{device_id}/network-control/history")
        assert history.status_code == 200
        assert [event["status"] for event in history.json()] == [
            "failed",
            "planned",
        ]
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def test_connected_devices_retains_offline_control_when_hotspot_is_unavailable(
    db_session, monkeypatch
):
    import api_network_control
    from db.session import get_db
    from main import app

    device = Device(
        ip_address="10.42.0.24",
        mac_address=MAC_A,
        network_subnet="10.42.0.0/24",
        is_current=False,
    )
    db_session.add(device)
    db_session.flush()
    db_session.add(
        DeviceNetworkControl(
            device_id=device.id,
            mode=MODE_INTERNET_ACCESS,
            action="block_internet",
            status="applied",
            target_ip="10.42.0.24",
            mac_address=MAC_A,
            network_subnet="10.42.0.0/24",
            interface="wlp2s0",
        )
    )
    db_session.commit()

    def override_db():
        yield db_session

    monkeypatch.setattr(
        api_network_control,
        "detect_network_topology",
        lambda: {"hotspot": None, "warnings": ["hotspot unavailable"]},
    )
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/api/network/devices")
        assert response.status_code == 200
        result = response.json()
        assert result["connected_device_count"] == 0
        assert len(result["devices"]) == 1
        assert result["devices"][0]["connection_status"] == "disconnected"
        assert result["devices"][0]["internet_access"] == "reconciliation_required"
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def test_network_context_uses_detected_hotspot_interface(monkeypatch):
    config = NetworkEnforcementConfig(
        enabled=False,
        dry_run=True,
        table="netra",
        interface=None,
        ifb=None,
        command_timeout_seconds=3,
        observation_ttl_seconds=300,
    )
    monkeypatch.setattr(NetworkEnforcementConfig, "from_env", lambda: config)
    topology = {
        "hotspot": {
            "active": True,
            "interface": "wlp2s0",
            "subnet": "10.42.0.0/24",
        }
    }

    _, effective, network, source = _network_context(topology)

    assert effective.interface == "wlp2s0"
    assert network == ipaddress.ip_network("10.42.0.0/24")
    assert source == "hotspot:wlp2s0"


def test_hotspot_inventory_persists_observations_and_separates_ip_reuse(db_session):
    topology = {"clients": [_client(MAC_A, "10.42.0.24")]}
    rows = _active_device_rows(db_session, topology, "wlp2s0", "10.42.0.0/24")

    assert len(rows) == 1
    first_id = rows[0]["device_id"]
    first = db_session.get(Device, first_id)
    assert first.mac_address == MAC_A
    assert first.discovery_source == "networkmanager-hotspot"
    assert db_session.query(DeviceObservation).count() == 1
    assert db_session.query(DeviceObservation).one().source == "hotspot:wlp2s0"

    topology = {"clients": [_client(MAC_B, "10.42.0.24")]}
    rows = _active_device_rows(db_session, topology, "wlp2s0", "10.42.0.0/24")

    assert len(rows) == 1
    assert rows[0]["device_id"] != first_id
    assert rows[0]["mac_address"] == MAC_B
    assert db_session.query(Device).count() == 2
    assert db_session.query(Device).filter(Device.is_current.is_(True)).count() == 1
    assert (
        db_session.query(Device).filter(Device.id == first_id).one().is_current is False
    )


def test_get_device_network_control_success_reports_verified_state(
    db_session, monkeypatch
):
    import api_network_control
    from db.session import get_db
    from main import app

    topology = {
        "hotspot": {
            "active": True,
            "interface": "wlp2s0",
            "subnet": "10.42.0.0/24",
        },
        "clients": [_client(MAC_A, "10.42.0.24")],
    }
    config = NetworkEnforcementConfig(
        enabled=False,
        dry_run=True,
        table="netra",
        interface=None,
        ifb=None,
        command_timeout_seconds=3,
        observation_ttl_seconds=300,
    )
    monkeypatch.setattr(
        api_network_control, "detect_network_topology", lambda: topology
    )
    monkeypatch.setattr(NetworkEnforcementConfig, "from_env", lambda: config)
    monkeypatch.setattr(
        api_network_control,
        "verify_internet_block",
        lambda *args, **kwargs: {
            "applied": True,
            "verified": True,
            "reasons": [],
            "rules_verified": True,
        },
    )

    def override_db():
        yield db_session

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app, client=("127.0.0.1", 54321))
        rows = _active_device_rows(db_session, topology, "wlp2s0", "10.42.0.0/24")
        device_id = rows[0]["device_id"]
        response = client.get(f"/api/devices/{device_id}/network-control")
        assert response.status_code == 200
        body = response.json()
        assert body["internet_access"] == "blocked"
        assert body["verified"] is True
        assert body["firewall_rules_installed"] is True
        assert body["physical_connectivity_confirmed"] is False
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def test_apply_endpoint_success_path_reports_helper_readiness(db_session, monkeypatch):
    import api_network_control
    from db.session import get_db
    from main import app

    topology = {
        "hotspot": {
            "active": True,
            "interface": "wlp2s0",
            "subnet": "10.42.0.0/24",
        },
        "clients": [_client(MAC_A, "10.42.0.24")],
    }
    config = NetworkEnforcementConfig(
        enabled=False,
        dry_run=True,
        table="netra",
        interface=None,
        ifb=None,
        command_timeout_seconds=3,
        observation_ttl_seconds=300,
    )
    monkeypatch.setattr(
        api_network_control, "detect_network_topology", lambda: topology
    )
    monkeypatch.setattr(NetworkEnforcementConfig, "from_env", lambda: config)
    monkeypatch.setattr(
        api_network_control,
        "apply_block_internet",
        lambda *args, **kwargs: {"status": "applied", "device_id": 1},
    )
    monkeypatch.setattr(
        api_network_control,
        "verify_internet_block",
        lambda *args, **kwargs: {
            "applied": True,
            "verified": True,
            "reasons": [],
            "rules_verified": True,
        },
    )

    def override_db():
        yield db_session

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app, client=("127.0.0.1", 54321))
        planned = client.post(
            "/api/devices/1/network-control/plan",
            json={"action": "block_internet"},
        )
        assert planned.status_code == 200
        plan_id = planned.json()["plan_id"]
        applied = client.post(
            "/api/devices/1/network-control/apply",
            json={
                "plan_id": plan_id,
                "action": "block_internet",
                "confirm": True,
                "approver": "tester",
            },
        )
        assert applied.status_code == 200
        body = applied.json()
        assert body["status"] == "applied"
        assert body["verified"] is True
        assert body["internet_access"] == "blocked"
        assert "configuration_ready" in body
        assert body["physical_connectivity_confirmed"] is False
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def test_network_context_rejects_mismatched_configured_interface(monkeypatch):
    config = NetworkEnforcementConfig(
        enabled=True,
        dry_run=False,
        table="netra",
        interface="enp3s0f1",
        ifb=None,
        command_timeout_seconds=3,
        observation_ttl_seconds=300,
    )
    monkeypatch.setattr(NetworkEnforcementConfig, "from_env", lambda: config)
    with pytest.raises(HTTPException) as exc:
        _network_context(
            {
                "hotspot": {
                    "active": True,
                    "interface": "wlp2s0",
                    "subnet": "10.42.0.0/24",
                }
            }
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "hotspot_interface_mismatch"
