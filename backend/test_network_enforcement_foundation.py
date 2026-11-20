import ipaddress
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import Base, Device, DeviceNetworkControl, DeviceObservation, DryRunPlan
from network_enforcement import commands, identity
from network_enforcement.config import NetworkEnforcementConfig
from network_enforcement.errors import CommandError, IdentityError, PlanError
from network_enforcement.service import (
    NetworkControlRequest,
    build_dry_run_plan,
    get_control_state,
)


MAC = "AA:BB:CC:DD:EE:01"
OTHER_MAC = "AA:BB:CC:DD:EE:02"
NOW = datetime(2026, 11, 19, 12, 0, 0)


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


@pytest.fixture
def authorized(monkeypatch):
    networks = [ipaddress.ip_network("10.200.0.0/24")]
    monkeypatch.setattr(
        identity.discovery_service,
        "get_authorized_networks",
        lambda: networks,
    )
    return networks


@pytest.fixture
def config():
    return NetworkEnforcementConfig(
        enabled=False,
        dry_run=True,
        table="netra",
        interface="netra-lan",
        ifb=None,
        command_timeout_seconds=1.5,
        observation_ttl_seconds=300,
    )


def make_device(
    db,
    *,
    device_id=None,
    ip="10.200.0.10",
    mac=MAC,
    subnet="10.200.0.0/24",
    observed_at=None,
    observation_ip=None,
    observation_mac=None,
    observation_subnet=None,
    is_current=True,
):
    device = Device(
        id=device_id,
        ip_address=ip,
        mac_address=mac,
        hostname="test-device",
        network_subnet=subnet,
        is_current=is_current,
        last_seen=NOW,
    )
    db.add(device)
    db.flush()
    db.add(
        DeviceObservation(
            device_id=device.id,
            ip_address=observation_ip or ip,
            mac_address=mac if observation_mac is None else observation_mac,
            network_subnet=observation_subnet or subnet,
            observed_at=observed_at or NOW,
            source="test",
        )
    )
    db.commit()
    return device


# Configuration


def test_config_defaults_are_disabled_and_dry_run():
    config = NetworkEnforcementConfig.from_env({})
    assert config.enabled is False
    assert config.dry_run is True
    assert config.apply_permitted is False
    assert config.table == "netra"
    assert config.interface is None
    assert config.ifb is None
    assert config.warnings == ()


def test_config_accepts_explicit_environment_values():
    config = NetworkEnforcementConfig.from_env(
        {
            "NETRA_NETWORK_ENFORCEMENT_ENABLED": "1",
            "NETRA_NETWORK_ENFORCEMENT_DRY_RUN": "false",
            "NETRA_NETWORK_ENFORCEMENT_TABLE": "netra_lab",
            "NETRA_NETWORK_ENFORCEMENT_INTERFACE": "netra-lan",
            "NETRA_NETWORK_ENFORCEMENT_IFB": "ifb0",
            "NETRA_NETWORK_ENFORCEMENT_COMMAND_TIMEOUT_SECONDS": "2.5",
            "NETRA_NETWORK_ENFORCEMENT_OBSERVATION_TTL_SECONDS": "120",
        }
    )
    assert config.apply_permitted is True
    assert config.table == "netra_lab"
    assert config.interface == "netra-lan"
    assert config.ifb == "ifb0"
    assert config.command_timeout_seconds == 2.5
    assert config.observation_ttl_seconds == 120
    assert config.warnings == ()


def test_config_invalid_values_fail_closed():
    config = NetworkEnforcementConfig.from_env(
        {
            "NETRA_NETWORK_ENFORCEMENT_ENABLED": "maybe",
            "NETRA_NETWORK_ENFORCEMENT_DRY_RUN": "false?",
            "NETRA_NETWORK_ENFORCEMENT_TABLE": "bad table",
            "NETRA_NETWORK_ENFORCEMENT_INTERFACE": "bad interface",
            "NETRA_NETWORK_ENFORCEMENT_COMMAND_TIMEOUT_SECONDS": "0",
            "NETRA_NETWORK_ENFORCEMENT_OBSERVATION_TTL_SECONDS": "1",
        }
    )
    assert config.enabled is False
    assert config.dry_run is True
    assert config.apply_permitted is False
    assert config.table == "netra"
    assert config.interface is None
    assert config.command_timeout_seconds == 3.0
    assert config.observation_ttl_seconds == 300
    assert len(config.warnings) == 6


# Identity validation


def test_resolve_device_target_accepts_consistent_identity(
    db_session, authorized, config
):
    device = make_device(db_session)
    target = identity.resolve_device_target(
        db_session, device.id, config=config, now=NOW
    )
    assert target.device_id == device.id
    assert target.ip_address == "10.200.0.10"
    assert target.mac_address == MAC
    assert target.network_subnet == "10.200.0.0/24"
    assert target.interface == "netra-lan"
    assert target.evidence["checks"]["fresh_observation"] is True


def test_resolve_device_target_requires_mac(db_session, authorized, config):
    device = make_device(db_session, mac=None)
    with pytest.raises(IdentityError) as exc:
        identity.resolve_device_target(db_session, device.id, config=config, now=NOW)
    assert exc.value.code == "missing_mac"


def test_resolve_device_target_rejects_public_ip(db_session, authorized, config):
    device = make_device(db_session, ip="8.8.8.8", subnet="8.8.8.0/24")
    with pytest.raises(IdentityError) as exc:
        identity.resolve_device_target(db_session, device.id, config=config, now=NOW)
    assert exc.value.code == "invalid_ip"


def test_resolve_device_target_rejects_unauthorized_private_ip(
    db_session, authorized, config
):
    device = make_device(db_session, ip="10.201.0.10", subnet="10.201.0.0/24")
    with pytest.raises(IdentityError) as exc:
        identity.resolve_device_target(db_session, device.id, config=config, now=NOW)
    assert exc.value.code == "unauthorized_ip"


def test_resolve_device_target_rejects_stale_observation(
    db_session, authorized, config
):
    device = make_device(db_session, observed_at=NOW - timedelta(seconds=301))
    with pytest.raises(IdentityError) as exc:
        identity.resolve_device_target(db_session, device.id, config=config, now=NOW)
    assert exc.value.code == "stale_observation"


def test_resolve_device_target_rejects_conflicting_observation(
    db_session, authorized, config
):
    device = make_device(db_session)
    make_device(
        db_session,
        ip="10.200.0.20",
        mac=OTHER_MAC,
        observation_ip="10.200.0.10",
        observation_mac=OTHER_MAC,
    )
    with pytest.raises(IdentityError) as exc:
        identity.resolve_device_target(db_session, device.id, config=config, now=NOW)
    assert exc.value.code == "observation_ip_conflict"


def test_resolve_device_target_rejects_observation_mac_mismatch(
    db_session, authorized, config
):
    device = make_device(db_session, observation_mac=OTHER_MAC)
    with pytest.raises(IdentityError) as exc:
        identity.resolve_device_target(db_session, device.id, config=config, now=NOW)
    assert exc.value.code == "observation_mac_conflict"


def test_resolve_device_target_requires_authorized_networks(
    db_session, monkeypatch, config
):
    monkeypatch.setattr(
        identity.discovery_service, "get_authorized_networks", lambda: []
    )
    device = make_device(db_session)
    with pytest.raises(IdentityError) as exc:
        identity.resolve_device_target(db_session, device.id, config=config, now=NOW)
    assert exc.value.code == "unauthorized_network"


def test_resolve_device_target_requires_configured_interface(db_session, authorized):
    device = make_device(db_session)
    bad_config = NetworkEnforcementConfig(
        enabled=False,
        dry_run=True,
        table="netra",
        interface=None,
        ifb=None,
        command_timeout_seconds=1.5,
        observation_ttl_seconds=300,
    )
    with pytest.raises(IdentityError) as exc:
        identity.resolve_device_target(
            db_session, device.id, config=bad_config, now=NOW
        )
    assert exc.value.code == "interface_not_configured"


# Safe command builders


def test_nft_builders_use_argument_lists_and_validated_values():
    assert commands.nft_list_table("netra").argv == (
        "nft",
        "-j",
        "list",
        "table",
        "inet",
        "netra",
    )
    assert commands.nft_add_element(
        "netra", "netra_blocked_v4", "10.200.0.10"
    ).argv == (
        "nft",
        "add",
        "element",
        "inet",
        "netra",
        "netra_blocked_v4",
        "{",
        "10.200.0.10",
        "}",
    )
    rules = commands.nft_block_rules(
        "netra",
        "netra_forward",
        "netra_dev_7",
        7,
        "netra-lan",
        "AA:BB:CC:DD:EE:01",
    )
    assert len(rules) == 4
    assert rules[0].argv[6:8] == ("iifname", '"netra-lan"')
    assert rules[1].argv[6:8] == ("oifname", '"netra-lan"')
    assert "saddr" in rules[0].argv
    assert "daddr" in rules[1].argv
    assert "netra-device-7-egress" in rules[0].argv[-1]
    assert "netra-device-7-ingress" in rules[1].argv[-1]
    assert rules[2].argv[6:8] == ("iifname", '"netra-lan"')
    assert "nfproto" in rules[2].argv and "ipv6" in rules[2].argv
    assert "netra-device-7-egress-ipv6" in rules[2].argv[-1]
    assert rules[3].argv[6:8] == ("oifname", '"netra-lan"')
    assert "nfproto" in rules[3].argv and "ipv6" in rules[3].argv
    assert "netra-device-7-ingress-ipv6" in rules[3].argv[-1]


def test_command_builders_reject_injected_values():
    with pytest.raises(CommandError):
        commands.nft_list_table("netra; flush ruleset")
    with pytest.raises(CommandError):
        commands.nft_add_element("netra", "set", "10.200.0.10; drop")
    with pytest.raises(CommandError):
        commands.nft_delete_rule("netra", "chain", "1; delete table")
    with pytest.raises(CommandError):
        commands.nft_block_rules(
            "netra",
            "chain",
            "set",
            7,
            "netra-lan; flush ruleset",
            "AA:BB:CC:DD:EE:01",
        )
    with pytest.raises(CommandError):
        commands.tc_add_class("eth0", "1:2", 0)
    with pytest.raises(CommandError):
        commands.tc_add_filter("eth0", "8.8.8.8", "1:2")
    with pytest.raises(CommandError):
        commands.tc_add_root_htb("eth0; tc qdisc del")


def test_tc_builders_are_device_specific_and_bounded():
    root = commands.tc_add_root_htb("netra-lan")
    assert root.argv[:5] == ("tc", "qdisc", "add", "dev", "netra-lan")
    assert "htb" in root.argv
    assert "add" in root.argv

    class_plan = commands.tc_add_class(
        "netra-lan", "1:a", 1000, root_handle="1:", ceil_kbps=2000
    )
    assert "1000kbit" in class_plan.argv
    assert "2000kbit" in class_plan.argv

    filter_plan = commands.tc_add_filter(
        "netra-lan", "10.200.0.10", "1:a", root_handle="1:", prio=12
    )
    assert "0ac8000a/ffffffff" in filter_plan.argv
    assert filter_plan.argv[filter_plan.argv.index("prio") + 1] == "12"


def test_run_command_uses_allowlisted_argv_no_shell_and_timeout(monkeypatch, config):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(commands.subprocess, "run", fake_run)
    result = commands.run_command(["nft", "-j", "list", "tables"], config)
    assert result.ok is True
    assert result.stdout == "ok"
    assert captured["argv"] == ["nft", "-j", "list", "tables"]
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["text"] is True
    assert captured["kwargs"]["timeout"] == 1.5


def test_run_command_rejects_non_allowlisted_commands():
    with pytest.raises(CommandError) as exc:
        commands.run_command(["sh", "-c", "nft list ruleset"])
    assert exc.value.code == "command_not_allowed"
    with pytest.raises(CommandError):
        commands.run_command("nft list ruleset")
    with pytest.raises(CommandError):
        commands.run_command(["nft", "list\x00ruleset"])


# Dry-run plans and additive state


def test_dry_run_block_plan_is_persisted_and_changes_nothing(
    db_session, authorized, config, monkeypatch
):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry-run must not execute commands")

    monkeypatch.setattr(commands.subprocess, "run", fail_if_called)
    device = make_device(db_session)
    record, plan, impact = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="block_internet"),
        config=config,
        now=NOW,
    )

    assert record.id is not None
    assert plan["mode"] == "dry-run"
    assert plan["action"] == "block_internet"
    assert plan["device"]["ip_address"] == "10.200.0.10"
    assert plan["apply_allowed"] is False
    assert plan["apply_blockers"] == [
        "NETRA_NETWORK_ENFORCEMENT_ENABLED is not true",
        "NETRA_NETWORK_ENFORCEMENT_DRY_RUN is true",
    ]
    assert plan["safety"]["shell_execution"] is False
    assert plan["safety"]["flushes_nftables_tables"] is False
    assert plan["safety"]["replaces_existing_qdiscs"] is False
    assert "nft" in " ".join(command["command"] for command in plan["commands"])
    assert impact["network_change"] is False

    assert db_session.query(DryRunPlan).count() == 1
    control = get_control_state(db_session, device.id, "internet_access")
    assert control is not None
    assert control.status == "planned"
    assert control.dry_run_plan_id == record.id
    assert control.target_ip == "10.200.0.10"


def test_dry_run_plan_respects_explicit_enable_and_no_dry_run(
    db_session, authorized, config, monkeypatch
):
    monkeypatch.setattr(
        commands.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("foundation stage must not execute commands")
        ),
    )
    enabled = NetworkEnforcementConfig(
        enabled=True,
        dry_run=False,
        table="netra",
        interface="netra-lan",
        ifb=None,
        command_timeout_seconds=1.5,
        observation_ttl_seconds=300,
    )
    device = make_device(db_session)
    _, plan, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="block_internet"),
        config=enabled,
        now=NOW,
    )
    assert plan["apply_allowed"] is True
    assert plan["apply_blockers"] == []


def test_dry_run_bandwidth_plan_uses_egress_htb_only(db_session, authorized, config):
    device = make_device(db_session)
    _, plan, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(
            device_id=device.id,
            action="set_bandwidth",
            upload_kbps=1000,
            download_kbps=2000,
        ),
        config=config,
        now=NOW,
    )
    commands_text = " ".join(command["command"] for command in plan["commands"])
    assert "tc qdisc add" in commands_text
    assert "htb" in commands_text
    assert "ingress" not in commands_text
    assert any("Ingress IFB" in warning for warning in plan["warnings"])
    assert plan["target_state"]["upload_kbps"] == 1000
    assert plan["target_state"]["download_kbps"] == 2000
    control = get_control_state(db_session, device.id, "bandwidth")
    assert control.status == "planned"
    assert control.upload_kbps == 1000
    assert control.download_kbps == 2000


def test_dry_run_restore_uses_recorded_rule_handles(db_session, authorized, config):
    device = make_device(db_session)
    db_session.add(
        DeviceNetworkControl(
            device_id=device.id,
            mode="internet_access",
            action="block_internet",
            status="applied",
            target_ip="10.200.0.10",
            nft_rule_handles_json=[12, 13],
        )
    )
    db_session.commit()

    _, plan, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="restore_internet"),
        config=config,
        now=NOW,
    )
    commands_text = " ".join(command["command"] for command in plan["commands"])
    assert "handle 12" in commands_text
    assert "handle 13" in commands_text
    assert plan["target_state"]["recorded_rule_handles"] == [12, 13]
    assert not any("No persisted Netra rule handles" in w for w in plan["warnings"])
    assert (
        get_control_state(db_session, device.id, "internet_access").status == "applied"
    )


def test_restore_plan_remains_available_when_dry_run_is_enabled(db_session, authorized):
    device = make_device(db_session)
    restore_config = NetworkEnforcementConfig(
        enabled=True,
        dry_run=True,
        table="netra",
        interface="netra-lan",
        ifb=None,
        command_timeout_seconds=1.5,
        observation_ttl_seconds=300,
    )

    _, plan, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="restore_internet"),
        config=restore_config,
        now=NOW,
    )

    assert plan["config"]["apply_permitted"] is False
    assert plan["apply_allowed"] is True
    assert plan["apply_blockers"] == []


def test_dry_run_remove_restrictions_spans_both_modes(db_session, authorized, config):
    device = make_device(db_session)
    _, plan, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="remove_restrictions"),
        config=config,
        now=NOW,
    )
    commands_text = " ".join(command["command"] for command in plan["commands"])
    assert "nft" in commands_text
    assert "tc" in commands_text
    assert plan["target_state"]["modes"] == ["internet_access", "bandwidth"]
    assert any("No persisted Netra rule handles" in w for w in plan["warnings"])
    assert any("HTB root qdisc" in w for w in plan["warnings"])
    assert get_control_state(db_session, device.id, "internet_access") is None
    assert get_control_state(db_session, device.id, "bandwidth") is None


def test_dry_run_rejects_invalid_requests(db_session, authorized, config):
    device = make_device(db_session)
    with pytest.raises(PlanError) as exc:
        build_dry_run_plan(
            db_session,
            NetworkControlRequest(device_id=device.id, action="flush_ruleset"),
            config=config,
            now=NOW,
        )
    assert exc.value.code == "unsupported_action"

    with pytest.raises(PlanError) as exc:
        build_dry_run_plan(
            db_session,
            NetworkControlRequest(
                device_id=device.id, action="set_bandwidth", upload_kbps=0
            ),
            config=config,
            now=NOW,
        )
    assert exc.value.code == "invalid_rate"

    with pytest.raises(PlanError) as exc:
        build_dry_run_plan(
            db_session,
            NetworkControlRequest(
                device_id=device.id,
                action="block_internet",
                download_kbps=1000,
            ),
            config=config,
            now=NOW,
        )
    assert exc.value.code == "unexpected_rate"
