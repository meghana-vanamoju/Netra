"""Tests for the restricted local helper and its unprivileged backend client."""

import os
import socket
import stat
import subprocess
import struct
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

import network_enforcement_helper as helper_module
from network_enforcement.config import NetworkEnforcementConfig
from network_enforcement.errors import HelperError, HelperPermissionError, NftablesError
from network_enforcement.target import DeviceTarget
from network_enforcement.nftables import NftablesAdapter
from network_enforcement.privileged_client import HelperClient, HelperNftablesAdapter
from network_enforcement.privileged_protocol import (
    PROTOCOL_VERSION,
    validate_request,
)
from network_enforcement_helper import (
    HelperConfig,
    HelperService,
    SnapshotStore,
    _HelperServer,
    build_server,
)
from test_network_enforcement_nftables import FakeNftRunner

IFACE = "wlp2s0"
TABLE = "netra"


def make_target(device_id=7, ip="10.42.0.24", mac="AA:BB:CC:DD:EE:24"):
    return DeviceTarget(
        device_id=device_id,
        ip_address=ip,
        mac_address=mac,
        network_subnet="10.42.0.0/24",
        interface=IFACE,
        observation_id=42,
        observed_at=None,
        source=f"hotspot:{IFACE}",
        evidence={},
    )


def helper_config(tmp_path=None, *, allowed_uids=None, allowed_gids=None):
    return HelperConfig(
        socket_path="/run/netra/network-enforcement.sock",
        allowed_uids=frozenset(allowed_uids or set()),
        allowed_gids=frozenset(allowed_gids or set()),
        allowed_table=TABLE,
        allowed_interface=IFACE,
        command_timeout_seconds=3.0,
        state_dir=str(tmp_path) if tmp_path is not None else None,
    )


def fake_helper_group(monkeypatch, gid=None):
    gid = os.getgid() if gid is None else gid
    calls = []

    class _Group:
        gr_gid = gid

    def getgrnam(name):
        calls.append(name)
        if name != helper_module.HELPER_SOCKET_GROUP:
            raise AssertionError(f"unexpected group lookup: {name}")
        return _Group()

    monkeypatch.setattr(helper_module.grp, "getgrnam", getgrnam)
    return gid, calls


def umask_spy(monkeypatch):
    real_umask = os.umask
    original = real_umask(0o022)
    real_umask(original)
    calls = []

    def spy(mask):
        calls.append(mask)
        return real_umask(mask)

    monkeypatch.setattr(helper_module.os, "umask", spy)
    return calls, original


def close_spy(monkeypatch):
    real_close = _HelperServer.server_close
    calls = []

    def spy(self):
        calls.append(True)
        return real_close(self)

    monkeypatch.setattr(_HelperServer, "server_close", spy)
    return calls


def request(operation, target=None, *, table=TABLE, snapshot=None):
    payload = {
        "protocol": PROTOCOL_VERSION,
        "operation": operation,
        "table": table,
    }
    if target is not None:
        payload["target"] = target
    if snapshot is not None:
        payload["snapshot"] = snapshot
    return payload


def target_payload(**overrides):
    target = make_target()
    data = {
        "device_id": target.device_id,
        "ip_address": target.ip_address,
        "mac_address": target.mac_address,
        "network_subnet": target.network_subnet,
        "interface": target.interface,
        "source": target.source,
        "observation_id": target.observation_id,
    }
    aliases = {"ip": "ip_address", "mac": "mac_address"}
    for key, value in overrides.items():
        data[aliases.get(key, key)] = value
    return data


class FakeAdapter:
    def __init__(self):
        self.calls = []
        self.snapshot_value = {
            "table": {"name": TABLE, "comment": "managed by Netra"},
            "set": {"name": "netra_dev_7", "elements": []},
            "rules": [],
        }
        self.block_value = {"status": "applied", "rules_created": 4}
        self.verify_value = {"applied": True, "verified": True, "family": ["ip", "ip6"]}
        self.restore_value = {"status": "restored", "rules_removed": 4}
        self.rollback_value = {"status": "rolled_back"}
        self.fail_block = False
        self.fail_restore = False
        self.active = 0
        self.max_active = 0

    def _enter(self):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        time.sleep(0.01)
        self.active -= 1

    def state_summary(self):
        self._enter()
        self.calls.append("state_summary")
        return {"table": {"name": TABLE}, "chain": []}

    def snapshot(self, target=None):
        self.calls.append(("snapshot", target.device_id))
        return dict(self.snapshot_value)

    def block(self, target):
        self.calls.append(("block", target.device_id))
        if self.fail_block:
            raise NftablesError("simulated partial apply", code="nftables_mutation_failed")
        return dict(self.block_value)

    def restore(self, target):
        self.calls.append(("restore", target.device_id))
        if self.fail_restore:
            raise NftablesError("simulated partial restore", code="nftables_mutation_failed")
        return dict(self.restore_value)

    def verify(self, target):
        self.calls.append(("verify", target.device_id))
        return dict(self.verify_value)

    def rollback(self, previous, target):
        self.calls.append(("rollback", target.device_id))
        return dict(self.rollback_value)


def make_service(tmp_path=None, adapter=None):
    service = HelperService(
        helper_config(tmp_path, allowed_uids={os.getuid()}),
        adapter_factory=lambda table, interface: adapter,
    )
    return service


def test_authenticate_uses_peer_credentials():
    service = HelperService(helper_config(allowed_uids={1234}, allowed_gids={}))
    credentials = struct.pack("3i", 99, 1234, 5678)
    assert service.authenticate(credentials) == {"uid": 1234, "gid": 5678}

    denied = HelperService(helper_config(allowed_uids={}, allowed_gids={}))
    response = denied.handle(request("inspect_state"), peer_credentials=credentials)
    assert response["ok"] is False
    assert response["error"]["code"] == "helper_caller_denied"

    group_allowed = HelperService(helper_config(allowed_gids={5678}))
    assert group_allowed.authenticate(credentials) == {"uid": 1234, "gid": 5678}


def test_real_unix_socket_peer_credentials(tmp_path, monkeypatch):
    fake_helper_group(monkeypatch)
    adapter = FakeAdapter()
    service = HelperService(
        helper_config(tmp_path, allowed_uids={os.getuid()}),
        adapter_factory=lambda table, interface: adapter,
    )
    server = build_server(
        HelperConfig(
            socket_path=str(tmp_path / "allowed.sock"),
            allowed_uids=frozenset({os.getuid()}),
            allowed_gids=frozenset(),
            allowed_table=TABLE,
            allowed_interface=IFACE,
            command_timeout_seconds=3.0,
            state_dir=None,
        ),
        service,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = HelperClient(str(tmp_path / "allowed.sock"), 3.0, TABLE).call(
            "verify_restriction", target=_ClientTarget(make_target(), TABLE)
        )
        assert result["verification"]["verified"] is True
    finally:
        server.shutdown()
        server.server_close()

    denied_service = HelperService(helper_config(allowed_uids={os.getuid() + 1}))
    denied_server = build_server(
        HelperConfig(
            socket_path=str(tmp_path / "denied.sock"),
            allowed_uids=frozenset({os.getuid() + 1}),
            allowed_gids=frozenset(),
            allowed_table=TABLE,
            allowed_interface=IFACE,
            command_timeout_seconds=3.0,
            state_dir=None,
        ),
        denied_service,
    )
    denied_thread = threading.Thread(target=denied_server.serve_forever, daemon=True)
    denied_thread.start()
    try:
        with pytest.raises(HelperError) as exc:
            HelperClient(str(tmp_path / "denied.sock"), 3.0, TABLE).call(
                "verify_restriction", target=_ClientTarget(make_target(), TABLE)
            )
        assert exc.value.code == "helper_caller_denied"
    finally:
        denied_server.shutdown()
        denied_server.server_close()


def test_build_server_sets_socket_group_permissions(tmp_path, monkeypatch):
    gid, group_calls = fake_helper_group(monkeypatch)
    umask_calls, original_umask = umask_spy(monkeypatch)
    socket_path = tmp_path / "secured.sock"
    parent_mode = stat.S_IMODE(tmp_path.stat().st_mode)
    config = replace(helper_config(tmp_path), socket_path=str(socket_path))

    server = build_server(config, make_service(tmp_path))
    try:
        info = socket_path.stat()
        assert stat.S_ISSOCK(info.st_mode)
        assert stat.S_IMODE(info.st_mode) == 0o660
        assert info.st_uid == os.getuid()
        assert info.st_gid == gid
        assert group_calls == ["netra-backend"]
        assert umask_calls == [0o077, original_umask]
        assert stat.S_IMODE(tmp_path.stat().st_mode) == parent_mode
    finally:
        server.server_close()

    assert not socket_path.exists()


def test_build_server_fails_closed_when_group_resolution_fails(tmp_path, monkeypatch):
    umask_calls, original_umask = umask_spy(monkeypatch)
    close_calls = close_spy(monkeypatch)
    socket_path = tmp_path / "no-group.sock"
    config = replace(helper_config(tmp_path), socket_path=str(socket_path))

    def fail_group(name):
        raise KeyError(name)

    monkeypatch.setattr(helper_module.grp, "getgrnam", fail_group)

    with pytest.raises(HelperPermissionError) as exc:
        build_server(config, make_service(tmp_path))

    assert exc.value.code == "helper_socket_group_unavailable"
    assert not socket_path.exists()
    assert close_calls == [True]
    assert umask_calls == [0o077, original_umask]


def test_build_server_fails_closed_without_unlinking_replacement(tmp_path, monkeypatch):
    gid, _ = fake_helper_group(monkeypatch, gid=os.getgid() + 1)
    umask_calls, original_umask = umask_spy(monkeypatch)
    close_calls = close_spy(monkeypatch)
    socket_path = tmp_path / "replaced.sock"
    config = replace(helper_config(tmp_path), socket_path=str(socket_path))

    def failing_chown(path, uid, expected_gid, **kwargs):
        assert path == socket_path.name
        assert kwargs.get("follow_symlinks") is False
        assert uid == os.getuid()
        assert expected_gid == gid
        os.unlink(socket_path)
        Path(socket_path).write_text("replacement", encoding="utf-8")
        raise OSError("simulated chown failure")

    monkeypatch.setattr(helper_module.os, "chown", failing_chown)

    with pytest.raises(HelperPermissionError) as exc:
        build_server(config, make_service(tmp_path))

    assert exc.value.code == "helper_socket_permission_failed"
    assert socket_path.read_text(encoding="utf-8") == "replacement"
    assert not stat.S_ISSOCK(socket_path.stat().st_mode)
    assert close_calls == [True]
    assert umask_calls == [0o077, original_umask]


def test_untargeted_inspect_state_preserves_readiness_response(tmp_path):
    adapter = FakeAdapter()
    service = make_service(tmp_path, adapter)
    service.store.save(7, {"table": {"name": TABLE}})

    response = service.handle(request("inspect_state"))

    assert response["ok"] is True
    assert response["operation"] == "inspect_state"
    assert response["result"] == {
        "state": {"table": {"name": TABLE}, "chain": []},
        "recoverable_devices": [7],
        "nftables_available": True,
    }
    assert "snapshot" not in response["result"]
    assert adapter.calls == ["state_summary"]


def test_targeted_inspect_state_returns_device_snapshot(tmp_path):
    adapter = FakeAdapter()
    service = make_service(tmp_path, adapter)

    response = service.handle(request("inspect_state", target_payload()))

    assert response["ok"] is True
    assert response["operation"] == "inspect_state"
    assert response["result"]["snapshot"] == adapter.snapshot_value
    assert ("snapshot", 7) in adapter.calls
    assert "state_summary" in adapter.calls
    assert response["result"]["nftables_available"] is True

    calls_after_valid = list(adapter.calls)
    invalid = service.handle(
        request("inspect_state", target_payload(ip_address="0.0.0.0"))
    )
    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "invalid_ip_address"
    assert adapter.calls == calls_after_valid


def test_block_internet_flow_gets_snapshot_over_real_helper_socket(
    tmp_path, monkeypatch
):
    fake_helper_group(monkeypatch)
    adapter = FakeAdapter()
    config = HelperConfig(
        socket_path=str(tmp_path / "block-flow.sock"),
        allowed_uids=frozenset({os.getuid()}),
        allowed_gids=frozenset(),
        allowed_table=TABLE,
        allowed_interface=IFACE,
        command_timeout_seconds=3.0,
        state_dir=str(tmp_path),
    )
    service = HelperService(config, adapter_factory=lambda table, interface: adapter)
    server = build_server(config, service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        helper_adapter = HelperNftablesAdapter(
            NetworkEnforcementConfig(
                enabled=True,
                dry_run=False,
                table=TABLE,
                interface=IFACE,
                ifb=None,
                command_timeout_seconds=3.0,
                observation_ttl_seconds=300,
            ),
            client=HelperClient(config.socket_path, 3.0, TABLE),
        )
        target = make_target()

        snapshot = helper_adapter.snapshot(target)
        assert snapshot == adapter.snapshot_value
        blocked = helper_adapter.block(target)
        assert blocked["status"] == "applied"
        assert blocked["rules_created"] == 4
        assert blocked["pre_snapshot"] == adapter.snapshot_value
        assert helper_adapter.verify(target) == adapter.verify_value
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class _ClientTarget:
    def __init__(self, target, table):
        self.target = target
        self.table = table

    def to_request(self):
        return {
            "device_id": self.target.device_id,
            "ip_address": self.target.ip_address,
            "mac_address": self.target.mac_address,
            "network_subnet": self.target.network_subnet,
            "interface": self.target.interface,
            "source": self.target.source,
            "observation_id": self.target.observation_id,
        }


@pytest.mark.parametrize(
    "payload",
    [
        ("shell_exec", request("shell_exec")),
        ("apply_restriction", {**request("apply_restriction"), "command": "nft flush ruleset"}),
        (
            "apply_restriction",
            request(
                "apply_restriction",
                target_payload(ip_address="0.0.0.0"),
            ),
        ),
        (
            "apply_restriction",
            request("apply_restriction", target_payload(network_subnet="0.0.0.0/0")),
        ),
        (
            "apply_restriction",
            request("apply_restriction", target_payload(source="dns")),
        ),
        (
            "apply_restriction",
            request("apply_restriction", target_payload(interface="docker0")),
        ),
        (
            "apply_restriction",
            request("apply_restriction", target_payload(device_id=0)),
        ),
        (
            "apply_restriction",
            request("apply_restriction", target_payload(observation_id=None)),
        ),
        ("apply_restriction", request("apply_restriction", target_payload(), table="filter")),
        (
            "apply_restriction",
            request("apply_restriction", target=target_payload(), snapshot={}),
        ),
    ],
)
def test_helper_rejects_malformed_or_unauthorized_operations(payload, tmp_path):
    adapter = FakeAdapter()
    service = make_service(tmp_path, adapter)
    response = service.handle(payload)
    assert response["ok"] is False
    assert adapter.calls == []


def test_wrong_interface_and_table_are_rejected_by_helper_config(tmp_path):
    adapter = FakeAdapter()
    service = make_service(tmp_path, adapter)
    wrong_iface = request("apply_restriction", target_payload(interface="docker0"))
    wrong_iface["target"]["source"] = "hotspot:docker0"
    assert service.handle(wrong_iface)["ok"] is False
    assert service.handle(request("apply_restriction", target_payload(), table="nat"))["ok"] is False
    assert adapter.calls == []


def test_apply_and_restore_are_scoped_to_one_device(tmp_path):
    adapter = FakeAdapter()
    service = make_service(tmp_path, adapter)
    target_a = target_payload(device_id=7)
    target_b = target_payload(device_id=8, ip="10.42.0.25", mac="AA:BB:CC:DD:EE:25")

    assert service.handle(request("apply_restriction", target_a))["ok"] is True
    assert ("block", 7) in adapter.calls
    assert ("block", 8) not in adapter.calls

    assert service.handle(request("restore_restriction", target_b))["ok"] is True
    assert ("restore", 8) in adapter.calls
    assert ("restore", 7) not in adapter.calls


def test_partial_apply_triggers_rollback_and_failure(tmp_path):
    adapter = FakeAdapter()
    adapter.fail_block = True
    service = make_service(tmp_path, adapter)
    response = service.handle(request("apply_restriction", target_payload()))
    assert response["ok"] is False
    assert response["error"]["code"] == "helper_apply_failed"
    assert ("rollback", 7) in adapter.calls


def test_partial_restore_keeps_snapshot_for_retry(tmp_path):
    adapter = FakeAdapter()
    adapter.fail_restore = True
    service = make_service(tmp_path, adapter)
    assert service.handle(request("apply_restriction", target_payload()))["ok"] is True
    response = service.handle(request("restore_restriction", target_payload()))
    assert response["ok"] is False
    assert SnapshotStore(str(tmp_path)).load(7) is not None


def test_snapshot_store_survives_service_restart(tmp_path):
    first = make_service(tmp_path, FakeAdapter())
    assert first.handle(request("apply_restriction", target_payload()))["ok"] is True

    adapter = FakeAdapter()
    restarted = make_service(tmp_path, adapter)
    readiness = restarted.handle(request("inspect_state"))
    assert readiness["result"]["recoverable_devices"] == [7]
    assert restarted.handle(request("rollback_restriction", target_payload()))["ok"] is True
    assert ("rollback", 7) in adapter.calls
    assert SnapshotStore(str(tmp_path)).load(7) is None


def test_helper_concurrent_requests_are_serialized(tmp_path):
    adapter = FakeAdapter()
    service = make_service(tmp_path, adapter)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(
                lambda _: service.handle(request("inspect_state")),
                range(6),
            )
        )
    assert all(result["ok"] for result in results)
    assert adapter.max_active == 1


def test_helper_unavailable_permission_and_timeout(monkeypatch, tmp_path):
    path = str(tmp_path / "missing.sock")
    with pytest.raises(HelperError) as unavailable:
        HelperClient(path, 1.0, TABLE).probe()
    assert unavailable.value.code == "helper_unavailable"

    def denied_connect(self, address):
        raise PermissionError("denied")

    monkeypatch.setattr(socket.socket, "connect", denied_connect)
    with pytest.raises(HelperError) as denied:
        HelperClient(path, 1.0, TABLE).probe()
    assert denied.value.code == "helper_permission_denied"
    monkeypatch.undo()

    def timeout_connect(self, address):
        raise socket.timeout("timed out")

    monkeypatch.setattr(socket.socket, "connect", timeout_connect)
    with pytest.raises(HelperError) as timeout:
        HelperClient(path, 1.0, TABLE).probe()
    assert timeout.value.code == "helper_timeout"


def test_backend_adapter_uses_helper_without_direct_firewall_access():
    config = NetworkEnforcementConfig(
        enabled=True,
        dry_run=False,
        table=TABLE,
        interface=IFACE,
        ifb=None,
        command_timeout_seconds=3.0,
        observation_ttl_seconds=300,
    )
    calls = []

    class FakeClient:
        def call(self, operation, *, target=None, snapshot=None):
            calls.append((operation, target.device.device_id))
            payloads = {
                "inspect_state": {"snapshot": {"rules": []}},
                "apply_restriction": {"result": {"status": "applied"}},
                "restore_restriction": {"result": {"status": "restored"}},
                "verify_restriction": {"verification": {"verified": True}},
                "rollback_restriction": {"result": {"status": "rolled_back"}},
            }
            return payloads[operation]

        def probe(self):
            calls.append(("probe", None))
            return {"state": {"table": {"name": TABLE}}}

    adapter = HelperNftablesAdapter(config, client=FakeClient())
    target = make_target()
    adapter.snapshot(target)
    adapter.block(target)
    adapter.restore(target)
    adapter.verify(target)
    adapter.rollback({"rules": []}, target)
    adapter.state_summary()
    assert [name for name, _ in calls] == [
        "inspect_state",
        "apply_restriction",
        "restore_restriction",
        "verify_restriction",
        "rollback_restriction",
        "probe",
    ]
    assert all(device_id == 7 for _, device_id in calls if device_id is not None)


def test_helper_real_nftables_adapter_keeps_ipv4_and_ipv6_rules(tmp_path):
    runner = FakeNftRunner(table_present=True, owned=True)
    service = HelperService(
        helper_config(tmp_path, allowed_uids={os.getuid()}),
        adapter_factory=lambda table, interface: NftablesAdapter(
            NetworkEnforcementConfig(
                enabled=True,
                dry_run=False,
                table=table,
                interface=interface,
                ifb=None,
                command_timeout_seconds=3.0,
                observation_ttl_seconds=300,
            ),
            runner,
        ),
    )
    response = service.handle(request("apply_restriction", target_payload()))
    assert response["ok"] is True, response
    result = response["result"]["result"]
    assert result["status"] == "applied"
    rules = result["rules"]
    assert len(rules) == 4
    ipv6_rules = [
        rule
        for rule in rules
        if any(
            expression.get("match", {})
            .get("left", {})
            .get("meta", {})
            .get("key")
            == "nfproto"
            for expression in rule["expr"]
        )
    ]
    assert len(ipv6_rules) == 2
    assert all(
        any(
            expression.get("match", {}).get("right") == "ipv6"
            for expression in rule["expr"]
        )
        for rule in ipv6_rules
    )
    assert SnapshotStore(str(tmp_path)).load(7) is not None


def test_helper_import_is_isolated_from_backend_database_and_discovery_stack():
    script = """
import sys
import network_enforcement_helper
bad = [
    name for name in sys.modules
    if name == 'sqlalchemy' or name.startswith('sqlalchemy.')
    or name == 'db' or name.startswith('db.')
    or name == 'discovery' or name.startswith('discovery.')
]
assert not bad, bad
assert 'network_enforcement.target' in sys.modules
print('ISOLATED')
"""
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "ISOLATED" in result.stdout


def test_identity_keeps_device_target_reexport():
    from network_enforcement.identity import DeviceTarget as LegacyDeviceTarget
    from network_enforcement.target import DeviceTarget

    assert LegacyDeviceTarget is DeviceTarget


def test_helper_rejects_unowned_table_from_existing_factory(tmp_path):
    runner = FakeNftRunner(table_present=True, owned=False)
    service = HelperService(
        helper_config(tmp_path, allowed_uids={os.getuid()}),
        adapter_factory=lambda table, interface: NftablesAdapter(
            NetworkEnforcementConfig(
                enabled=True,
                dry_run=False,
                table=table,
                interface=interface,
                ifb=None,
                command_timeout_seconds=3.0,
                observation_ttl_seconds=300,
            ),
            runner,
        ),
    )
    response = service.handle(request("apply_restriction", target_payload()))
    assert response["ok"] is False
    assert response["error"]["code"] in {"table_conflict", "helper_apply_failed"}
    assert runner.mutation_count == 0
