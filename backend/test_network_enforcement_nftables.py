import ipaddress
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import Base, ConfigSnapshot, Device, DeviceObservation
from network_enforcement import identity, nftables as nftables_module
from network_enforcement.config import NetworkEnforcementConfig
from network_enforcement.constants import device_set_name
from network_enforcement.commands import CommandResult
from network_enforcement.errors import (
    CommandError,
    IdentityError,
    NftablesError,
    PlanError,
)
from network_enforcement.target import DeviceTarget
from network_enforcement.nftables import NftablesAdapter
from network_enforcement.service import (
    NetworkControlRequest,
    apply_block_internet,
    apply_restore_internet,
    build_dry_run_plan,
    get_control_state,
    rollback_internet_control,
    verify_internet_block,
)

NOW = datetime(2026, 11, 19, 12, 0, 0)
TABLE = "netra"
SET = "netra_blocked_v4"
CHAIN = "netra_forward"
DROP = {"drop": None}


def interface_match(key, interface):
    return {
        "match": {
            "op": "==",
            "left": {"meta": {"key": key}},
            "right": interface,
        }
    }


def payload_match(field, right):
    return {
        "match": {
            "op": "==",
            "left": {"payload": {"protocol": "ip", "field": field}},
            "right": right,
        }
    }


def ether_match(field, mac):
    return {
        "match": {
            "op": "==",
            "left": {"payload": {"protocol": "ether", "field": field}},
            "right": mac,
        }
    }


def set_match(field, set_name=None):
    set_name = set_name or device_set_name(7)
    return payload_match(field, f"@{set_name}")


def make_target(device_id=7, ip="10.200.0.10", mac="AA:BB:CC:DD:EE:01"):
    return DeviceTarget(
        device_id=device_id,
        ip_address=ip,
        mac_address=mac,
        network_subnet="10.200.0.0/24",
        interface="netra-lan",
        observation_id=1,
        observed_at=NOW,
        source="test",
        evidence={},
    )


class FakeNftRunner:
    """In-memory nftables stand-in used only by tests."""

    def __init__(
        self,
        *,
        table_present=False,
        owned=True,
        set_present=False,
        chain_present=False,
        elements=None,
        rules=None,
        chain_policy="accept",
        chain_family="inet",
        chain_type="filter",
        chain_hook="forward",
        chain_priority=10,
        chain_table=TABLE,
        chain_name=CHAIN,
    ):
        self.table_present = table_present
        self.owned = owned
        self.set_present = set_present
        self.chain_present = chain_present
        self.default_elements = set(elements or [])
        self.sets = {}
        self.rules = [dict(rule) for rule in (rules or [])]
        self.chain_policy = chain_policy
        self.chain_family = chain_family
        self.chain_type = chain_type
        self.chain_hook = chain_hook
        self.chain_priority = chain_priority
        self.chain_table = chain_table
        self.chain_name = chain_name
        self.next_handle = 10
        self.log = []
        self.mutation_count = 0
        self.fail_mutation_at = None
        self.fail_with_exception = False

    @property
    def elements(self):
        elements = set(self.default_elements if self.set_present else [])
        for values in self.sets.values():
            elements.update(values)
        return elements

    def _json(self, *entries):
        return json.dumps({"nftables": [{"metainfo": {}}, *entries]})

    def _rule_expr(self, argv):
        direction = "iifname" if "iifname" in argv else "oifname"
        if direction not in argv:
            return []
        iface = argv[argv.index(direction) + 1].strip('"')
        mac_direction = "saddr" if direction == "iifname" else "daddr"
        mac = argv[argv.index("ether") + 2]
        field = "saddr" if direction == "iifname" else "daddr"
        if "nfproto" in argv:
            protocol_match = {
                "match": {
                    "op": "==",
                    "left": {"meta": {"key": "nfproto"}},
                    "right": "ipv6",
                }
            }
        else:
            set_name = argv[argv.index("ip") + 2].removeprefix("@")
            protocol_match = {
                "match": {
                    "op": "==",
                    "left": {"payload": {"protocol": "ip", "field": field}},
                    "right": f"@{set_name}",
                }
            }
        return [
            {
                "match": {
                    "op": "==",
                    "left": {"meta": {"key": direction}},
                    "right": iface,
                }
            },
            {
                "match": {
                    "op": "==",
                    "left": {"payload": {"protocol": "ether", "field": mac_direction}},
                    "right": mac,
                }
            },
            protocol_match,
            {"drop": None},
        ]

    def _missing(self, argv):
        return CommandResult(tuple(argv), 1, "", "No such file or directory")

    def __call__(self, argv, config=None):
        argv = list(argv)
        self.log.append(argv)

        is_mutation = len(argv) > 2 and argv[1] in {"add", "delete"}
        if is_mutation:
            self.mutation_count += 1
            if self.mutation_count == self.fail_mutation_at:
                self.fail_mutation_at = None
                if self.fail_with_exception:
                    raise CommandError("Command timed out", code="command_timeout")
                return CommandResult(tuple(argv), 1, "", "injected command failure")

        if argv[:3] == ["nft", "-j", "list"]:
            kind = argv[3]
            if not self.table_present:
                return self._missing(argv)
            if kind == "table":
                entry = {
                    "table": {
                        "family": "inet",
                        "name": TABLE,
                        "handle": 1,
                        "comment": "netra-managed" if self.owned else "foreign",
                    }
                }
                return CommandResult(tuple(argv), 0, self._json(entry), "")
            if kind == "set":
                set_name = argv[-1]
                if set_name not in self.sets and not (
                    self.set_present and set_name == SET
                ):
                    return self._missing(argv)
                elements = self.sets.get(set_name, self.default_elements)
                entry = {
                    "set": {
                        "family": "inet",
                        "table": TABLE,
                        "name": set_name,
                        "type": "ipv4_addr",
                        "handle": 2,
                        "comment": "netra-managed" if self.owned else "foreign",
                        "elem": sorted(elements),
                    }
                }
                return CommandResult(tuple(argv), 0, self._json(entry), "")
            if kind == "chain":
                if not self.chain_present:
                    return self._missing(argv)
                entries = [
                    {
                        "chain": {
                            "family": self.chain_family,
                            "table": self.chain_table,
                            "name": self.chain_name,
                            "handle": 3,
                            "comment": "netra-managed" if self.owned else "foreign",
                            "type": self.chain_type,
                            "hook": self.chain_hook,
                            "prio": self.chain_priority,
                            "policy": self.chain_policy,
                        }
                    }
                ]
                entries.extend(
                    {
                        "rule": {
                            "family": "inet",
                            "table": TABLE,
                            "chain": CHAIN,
                            "handle": rule["handle"],
                            "comment": rule["comment"],
                            "expr": rule.get("expr", []),
                        }
                    }
                    for rule in self.rules
                )
                return CommandResult(tuple(argv), 0, self._json(*entries), "")

        if argv[1] == "add" and argv[2] == "table":
            self.table_present = True
            self.owned = True
            return CommandResult(tuple(argv), 0, "", "")
        if argv[1] == "add" and argv[2] == "set":
            self.sets.setdefault(argv[5], set())
            return CommandResult(tuple(argv), 0, "", "")
        if argv[1] == "add" and argv[2] == "chain":
            self.chain_present = True
            self.chain_policy = "accept"
            self.chain_family = "inet"
            self.chain_type = "filter"
            self.chain_hook = "forward"
            self.chain_priority = 10
            return CommandResult(tuple(argv), 0, "", "")
        if argv[1] == "add" and argv[2] == "element":
            self.sets.setdefault(argv[5], set(self.default_elements)).add(argv[7])
            return CommandResult(tuple(argv), 0, "", "")
        if argv[1] == "delete" and argv[2] == "element":
            self.sets.setdefault(argv[5], set(self.default_elements)).discard(argv[7])
            return CommandResult(tuple(argv), 0, "", "")
        if argv[1] == "add" and argv[2] == "rule":
            comment = argv[-1].strip('"')
            self.rules.append(
                {
                    "comment": comment,
                    "handle": self.next_handle,
                    "expr": self._rule_expr(argv),
                }
            )
            self.next_handle += 1
            return CommandResult(tuple(argv), 0, "", "")
        if argv[1] == "delete" and argv[2] == "rule":
            handle = int(argv[-1])
            self.rules = [rule for rule in self.rules if rule["handle"] != handle]
            return CommandResult(tuple(argv), 0, "", "")

        return CommandResult(tuple(argv), 1, "", "unsupported fake command")


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
        identity.discovery_service, "get_authorized_networks", lambda: networks
    )
    return networks


@pytest.fixture
def enabled_config():
    return NetworkEnforcementConfig(
        enabled=True,
        dry_run=False,
        table=TABLE,
        interface="netra-lan",
        ifb=None,
        command_timeout_seconds=1.5,
        observation_ttl_seconds=300,
    )


def make_device(db, device_id=None, ip="10.200.0.10", mac="AA:BB:CC:DD:EE:01"):
    device = Device(
        id=device_id,
        ip_address=ip,
        mac_address=mac,
        hostname="test-device",
        network_subnet="10.200.0.0/24",
        is_current=True,
        last_seen=NOW,
    )
    db.add(device)
    db.flush()
    db.add(
        DeviceObservation(
            device_id=device.id,
            ip_address=ip,
            mac_address=mac,
            network_subnet="10.200.0.0/24",
            observed_at=NOW,
            source="test",
        )
    )
    db.commit()
    return device


# Adapter tests


def test_block_creates_owned_table_set_chain_and_tagged_rules(enabled_config):
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    target = make_target()

    result = adapter.block(target)

    assert result["status"] == "applied"
    assert result["rule_handles"] == [10, 11, 12, 13]
    assert runner.elements == {"10.200.0.10"}
    assert [rule["comment"] for rule in runner.rules] == [
        "netra-device-7-egress",
        "netra-device-7-ingress",
        "netra-device-7-egress-ipv6",
        "netra-device-7-ingress-ipv6",
    ]
    assert adapter.verify(target)["verified"] is True
    assert not any("flush" in " ".join(argv) for argv in runner.log)
    assert not any(argv[:3] == ["nft", "delete", "table"] for argv in runner.log)


def test_block_is_idempotent(enabled_config):
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    target = make_target()

    first = adapter.block(target)
    second = adapter.block(target)

    assert first["rule_handles"] == second["rule_handles"]
    assert len(runner.rules) == 4
    assert runner.elements == {"10.200.0.10"}


def test_block_rules_are_scoped_to_configured_interface(enabled_config):
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    target = make_target()

    result = adapter.block(target)

    assert result["interface"] == "netra-lan"
    assert all(rule["scoped"] for rule in result["rules"])
    assert runner.rules[0]["expr"][0]["match"]["left"]["meta"]["key"] == "iifname"
    assert runner.rules[0]["expr"][0]["match"]["right"] == "netra-lan"
    assert runner.rules[0]["expr"][1]["match"]["left"]["payload"]["field"] == "saddr"
    assert runner.rules[0]["expr"][1]["match"]["right"] == target.mac_address
    assert runner.rules[0]["expr"][2]["match"]["right"] == f"@{device_set_name(7)}"
    assert runner.rules[0]["expr"][3] == DROP
    assert runner.rules[1]["expr"][0]["match"]["left"]["meta"]["key"] == "oifname"
    assert runner.rules[1]["expr"][0]["match"]["right"] == "netra-lan"
    assert runner.rules[1]["expr"][1]["match"]["left"]["payload"]["field"] == "daddr"
    assert runner.rules[1]["expr"][1]["match"]["right"] == target.mac_address
    assert runner.rules[1]["expr"][2]["match"]["right"] == f"@{device_set_name(7)}"
    assert runner.rules[1]["expr"][3] == DROP
    assert runner.rules[2]["expr"][0]["match"]["right"] == "netra-lan"
    assert runner.rules[2]["expr"][2]["match"]["right"] == "ipv6"
    assert runner.rules[3]["expr"][0]["match"]["right"] == "netra-lan"
    assert runner.rules[3]["expr"][2]["match"]["right"] == "ipv6"
    assert adapter.verify(target)["verified"] is True


def test_rule_scope_accepts_canonical_json_expression_shape():
    egress = [
        interface_match("iifname", "netra-lan"),
        ether_match("saddr", "AA:BB:CC:DD:EE:01"),
        set_match("saddr"),
        DROP,
    ]
    ingress = [
        interface_match("oifname", "netra-lan"),
        ether_match("daddr", "AA:BB:CC:DD:EE:01"),
        set_match("daddr"),
        DROP,
    ]

    assert (
        nftables_module._rule_scope(
            {"expr": egress}, "netra-device-7-egress", "netra-lan"
        )
        is True
    )
    assert (
        nftables_module._rule_scope(
            {"expr": ingress}, "netra-device-7-ingress", "netra-lan"
        )
        is True
    )
    assert (
        nftables_module._rule_scope(
            {"expr": egress}, "netra-device-7-ingress", "netra-lan"
        )
        is False
    )


@pytest.mark.parametrize(
    "expression",
    [
        # All expected strings are present, but the interface key is wrong.
        [
            interface_match("oifname", "netra-lan"),
            ether_match("saddr", "AA:BB:CC:DD:EE:01"),
            set_match("saddr"),
            DROP,
        ],
        # All expected strings are present, but the payload field is wrong.
        [
            interface_match("iifname", "netra-lan"),
            ether_match("saddr", "AA:BB:CC:DD:EE:01"),
            set_match("daddr"),
            DROP,
        ],
        # Interface and set references are swapped between positions.
        [
            interface_match("iifname", f"@{SET}"),
            ether_match("saddr", "AA:BB:CC:DD:EE:01"),
            payload_match("saddr", "netra-lan"),
            DROP,
        ],
        # The drop verdict appears before the two matches.
        [
            DROP,
            interface_match("iifname", "netra-lan"),
            ether_match("saddr", "AA:BB:CC:DD:EE:01"),
            set_match("saddr"),
        ],
        # Substring matches would accept these near misses.
        [
            interface_match("iifname", "netra-lan-extra"),
            ether_match("saddr", "AA:BB:CC:DD:EE:01"),
            set_match("saddr"),
            DROP,
        ],
        [
            interface_match("iifname", "netra-lan"),
            ether_match("saddr", "AA:BB:CC:DD:EE:01"),
            set_match("saddr", f"{device_set_name(7)}_extra"),
            DROP,
        ],
        # Incomplete expression.
        [
            interface_match("iifname", "netra-lan"),
            ether_match("saddr", "AA:BB:CC:DD:EE:01"),
            set_match("saddr"),
        ],
        # Extra statement after the expected three.
        [
            interface_match("iifname", "netra-lan"),
            ether_match("saddr", "AA:BB:CC:DD:EE:01"),
            set_match("saddr"),
            DROP,
            {"accept": None},
        ],
        # Malformed statement carrying an unexpected extra key.
        [
            {
                **interface_match("iifname", "netra-lan"),
                "comment": "unexpected",
            },
            ether_match("saddr", "AA:BB:CC:DD:EE:01"),
            set_match("saddr"),
            DROP,
        ],
    ],
)
def test_rule_scope_rejects_malformed_or_misordered_expressions(expression):
    assert (
        nftables_module._rule_scope(
            {"expr": expression}, "netra-device-7-egress", "netra-lan"
        )
        is False
    )


def test_rule_scope_rejects_non_list_expression():
    expression = {
        "iifname": "netra-lan",
        "ether_saddr": "AA:BB:CC:DD:EE:01",
        "saddr": f"@{SET}",
        "drop": True,
    }
    assert (
        nftables_module._rule_scope(
            {"expr": expression}, "netra-device-7-egress", "netra-lan"
        )
        is False
    )


def test_block_requires_a_configured_interface():
    config = NetworkEnforcementConfig(
        enabled=True,
        dry_run=False,
        table=TABLE,
        interface=None,
        ifb=None,
        command_timeout_seconds=1.5,
        observation_ttl_seconds=300,
    )
    runner = FakeNftRunner()
    adapter = NftablesAdapter(config, runner)

    with pytest.raises(NftablesError) as exc:
        adapter.block(make_target())
    assert exc.value.code == "interface_not_configured"
    assert runner.log == []


def test_block_refuses_existing_unscoped_rule(enabled_config):
    runner = FakeNftRunner(
        table_present=True,
        set_present=True,
        chain_present=True,
        rules=[
            {
                "comment": "netra-device-7-egress",
                "handle": 10,
                "expr": [],
            }
        ],
    )
    adapter = NftablesAdapter(enabled_config, runner)

    with pytest.raises(NftablesError) as exc:
        adapter.block(make_target())

    assert exc.value.code == "unscoped_rule_conflict"
    assert [argv for argv in runner.log if argv[1:3] == ["add", "rule"]] == []
    assert runner.elements == set()
    assert [rule["comment"] for rule in runner.rules] == ["netra-device-7-egress"]


def test_restore_removes_legacy_unscoped_rules(enabled_config):
    runner = FakeNftRunner(
        table_present=True,
        set_present=True,
        chain_present=True,
        elements=["10.200.0.10"],
        rules=[
            {
                "comment": "netra-device-7-egress",
                "handle": 10,
                "expr": [],
            },
            {
                "comment": "netra-device-7-ingress",
                "handle": 11,
                "expr": [],
            },
        ],
    )
    adapter = NftablesAdapter(enabled_config, runner)

    result = adapter.restore(make_target())

    assert result["status"] == "restored"
    assert runner.rules == []
    assert runner.elements == {"10.200.0.10"}
    assert device_set_name(7) not in runner.sets


def test_verify_flags_legacy_unscoped_rules(enabled_config):
    runner = FakeNftRunner(
        table_present=True,
        set_present=True,
        chain_present=True,
        elements=["10.200.0.10"],
        rules=[
            {
                "comment": "netra-device-7-egress",
                "handle": 10,
                "expr": [],
            }
        ],
    )
    adapter = NftablesAdapter(enabled_config, runner)

    verification = adapter.verify(make_target())

    assert verification["verified"] is False
    assert "unscoped_rules_present" in verification["reasons"]
    assert verification["applied"] is True


def test_dry_run_block_plan_is_interface_scoped(db_session, authorized, enabled_config):
    device = make_device(db_session)
    _, plan, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="block_internet"),
        config=enabled_config,
        now=NOW,
    )

    rule_argv = [
        command["argv"]
        for command in plan["commands"]
        if command["argv"][1:3] == ["add", "rule"]
    ]
    assert len(rule_argv) == 4
    assert rule_argv[0][6:8] == ["iifname", '"netra-lan"']
    assert rule_argv[1][6:8] == ["oifname", '"netra-lan"']
    assert plan["target_state"]["nft_interface"] == "netra-lan"
    assert not any(
        token in command["argv"]
        for command in plan["commands"]
        for token in ("docker0", "eth0", "netra-wan")
    )


def test_block_refuses_foreign_table(enabled_config):
    runner = FakeNftRunner(table_present=True, owned=False)
    adapter = NftablesAdapter(enabled_config, runner)

    with pytest.raises(NftablesError) as exc:
        adapter.block(make_target())
    assert exc.value.code == "table_conflict"
    assert not any(argv[1] == "add" for argv in runner.log)


def test_block_refuses_foreign_chain_policy(enabled_config):
    runner = FakeNftRunner(
        table_present=True,
        set_present=True,
        chain_present=True,
        chain_policy="drop",
    )
    adapter = NftablesAdapter(enabled_config, runner)

    with pytest.raises(NftablesError) as exc:
        adapter.block(make_target())
    assert exc.value.code == "chain_policy_conflict"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("chain_family", "ip"),
        ("chain_table", "foreign"),
        ("chain_name", "other_forward"),
        ("chain_type", "nat"),
        ("chain_hook", "input"),
        ("chain_priority", 20),
    ],
)
def test_block_refuses_incorrect_forward_chain_configuration(
    enabled_config, field, value
):
    runner = FakeNftRunner(table_present=True, set_present=True, chain_present=True)
    setattr(runner, field, value)
    adapter = NftablesAdapter(enabled_config, runner)

    with pytest.raises(NftablesError) as exc:
        adapter.block(make_target())

    assert exc.value.code == "chain_configuration_conflict"
    assert not any(argv[1:3] == ["add", "rule"] for argv in runner.log)


def test_verify_rejects_missing_forward_chain(enabled_config):
    runner = FakeNftRunner(table_present=True, set_present=True, chain_present=False)
    adapter = NftablesAdapter(enabled_config, runner)

    verification = adapter.verify(make_target())

    assert verification["verified"] is False
    assert "chain_absent" in verification["reasons"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("chain_family", "ip"),
        ("chain_table", "foreign"),
        ("chain_name", "other_forward"),
        ("chain_type", "nat"),
        ("chain_hook", "input"),
        ("chain_priority", 20),
        ("chain_policy", "drop"),
    ],
)
def test_verify_rejects_incorrect_forward_chain_configuration(
    enabled_config, field, value
):
    runner = FakeNftRunner(table_present=True, set_present=True, chain_present=True)
    setattr(runner, field, value)
    adapter = NftablesAdapter(enabled_config, runner)

    verification = adapter.verify(make_target())

    assert verification["verified"] is False
    assert "chain_configuration_mismatch" in verification["reasons"]


def test_restore_removes_only_target_device_rules(enabled_config):
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    target_a = make_target(7, "10.200.0.10")
    target_b = make_target(8, "10.200.0.11", "AA:BB:CC:DD:EE:02")

    adapter.block(target_a)
    adapter.block(target_b)
    result = adapter.restore(target_a)

    assert result["status"] == "restored"
    assert [rule["comment"] for rule in runner.rules] == [
        "netra-device-8-egress",
        "netra-device-8-ingress",
        "netra-device-8-egress-ipv6",
        "netra-device-8-ingress-ipv6",
    ]
    assert runner.elements == {"10.200.0.11"}
    assert adapter.verify(target_a)["verified"] is False
    assert adapter.verify(target_b)["verified"] is True


def test_restore_rejects_unexpected_recorded_handle(enabled_config):
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    target_a = make_target(7, "10.200.0.10")
    target_b = make_target(8, "10.200.0.11", "AA:BB:CC:DD:EE:02")

    adapter.block(target_a)
    handles = [rule["handle"] for rule in runner.rules]
    adapter.block(target_b)

    with pytest.raises(NftablesError) as exc:
        adapter.restore(target_b, handles=handles)
    assert exc.value.code == "unexpected_rule_handle"
    assert len(runner.rules) == 8


def test_verify_reports_absent_table_without_changes(enabled_config):
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)

    verification = adapter.verify(make_target())

    assert verification["verified"] is False
    assert verification["applied"] is False
    assert verification["reasons"] == ["table_absent"]
    assert runner.log and all(argv[1] == "-j" for argv in runner.log)


def test_snapshot_contains_only_netra_state(enabled_config):
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    adapter.block(make_target())

    snapshot = adapter.snapshot(make_target())

    assert snapshot["backend"] == "network:nftables"
    assert snapshot["table_present"] is True
    assert snapshot["owned"] is True
    assert snapshot["elements"] == ["10.200.0.10"]
    assert [rule["comment"] for rule in snapshot["rules"]] == [
        "netra-device-7-egress",
        "netra-device-7-ingress",
        "netra-device-7-egress-ipv6",
        "netra-device-7-ingress-ipv6",
    ]
    assert all(rule["scoped"] for rule in snapshot["rules"])
    assert snapshot["interface"] == "netra-lan"
    assert "ruleset" not in snapshot


def test_rollback_removes_target_state_from_snapshot(enabled_config):
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    target = make_target()
    before = adapter.snapshot(target)

    adapter.block(target)
    result = adapter.rollback(before, target)

    assert result["status"] == "rolled_back"
    assert runner.elements == set()
    assert runner.rules == []
    assert adapter.verify(target)["applied"] is False


def test_rollback_rejects_snapshot_for_different_table(enabled_config):
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    target = make_target()
    previous = adapter.snapshot(target)
    previous["table"] = "other"

    with pytest.raises(NftablesError) as exc:
        adapter.rollback(previous, target)

    assert exc.value.code == "snapshot_table_mismatch"
    assert not any(argv[1] in {"add", "delete"} for argv in runner.log)


def test_rollback_preserves_matching_scoped_rules(enabled_config):
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    target = make_target()
    adapter.block(target)
    previous = adapter.snapshot(target)

    adapter.block(target)
    result = adapter.rollback(previous, target)

    assert result["status"] == "no_change"
    assert len(runner.rules) == 4
    assert all(
        nftables_module._rule_scope(
            rule,
            rule["comment"],
            "netra-lan",
            device_set_name(target.device_id),
            target.mac_address,
        )
        for rule in runner.rules
    )
    assert adapter.verify(target)["verified"] is True


def test_rollback_recreates_a_deleted_prior_rule(enabled_config):
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    target = make_target()
    adapter.block(target)
    previous = adapter.snapshot(target)
    runner.rules.pop(0)

    result = adapter.rollback(previous, target)

    assert result["status"] == "rolled_back"
    assert {rule["comment"] for rule in runner.rules} == {
        "netra-device-7-egress",
        "netra-device-7-ingress",
        "netra-device-7-egress-ipv6",
        "netra-device-7-ingress-ipv6",
    }
    assert adapter.verify(target)["verified"] is True


def test_rollback_rejects_interface_scope_mismatch(enabled_config):
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    target = make_target()
    adapter.block(target)
    previous = adapter.snapshot(target)

    for rule in runner.rules:
        rule["expr"] = []

    with pytest.raises(NftablesError) as exc:
        adapter.rollback(previous, target)
    assert exc.value.code == "rollback_verification_failed"
    assert not any(argv[1:3] == ["delete", "rule"] for argv in runner.log)


def test_restoration_stays_available_while_dry_run_is_enabled(enabled_config):
    dry_config = NetworkEnforcementConfig(
        enabled=True,
        dry_run=True,
        table=TABLE,
        interface="netra-lan",
        ifb=None,
        command_timeout_seconds=1.5,
        observation_ttl_seconds=300,
    )
    runner = FakeNftRunner()
    target = make_target()

    NftablesAdapter(enabled_config, runner).block(target)
    result = NftablesAdapter(dry_config, runner).restore(target)

    assert result["status"] == "restored"
    assert runner.elements == set()
    assert runner.rules == []


def test_adapter_requires_explicit_opt_in():
    config = NetworkEnforcementConfig(
        enabled=False,
        dry_run=True,
        table=TABLE,
        interface="netra-lan",
        ifb=None,
        command_timeout_seconds=1.5,
        observation_ttl_seconds=300,
    )
    runner = FakeNftRunner()
    adapter = NftablesAdapter(config, runner)

    with pytest.raises(NftablesError) as exc:
        adapter.block(make_target())
    assert exc.value.code == "apply_not_permitted"
    assert runner.log == []


# Service apply / rollback tests


def test_apply_block_snapshot_and_control_state(db_session, authorized, enabled_config):
    device = make_device(db_session)
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    plan, _, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="block_internet"),
        config=enabled_config,
        now=NOW,
    )

    result = apply_block_internet(
        db_session,
        device.id,
        plan_id=plan.id,
        approver="tester",
        config=enabled_config,
        now=NOW,
        adapter=adapter,
    )

    assert result["status"] == "applied"
    assert result["verification"]["verified"] is True
    assert result["consent"] == {"approver": "tester", "plan_id": plan.id}
    snapshot = db_session.query(ConfigSnapshot).one()
    assert snapshot.backend == "network:nftables"
    assert snapshot.checksum
    control = get_control_state(db_session, device.id, "internet_access")
    assert control.status == "applied"
    assert control.snapshot_id == snapshot.id
    assert control.nft_rule_handles_json == [10, 11, 12, 13]


@pytest.mark.parametrize("fail_with_exception", [False, True])
def test_apply_block_rolls_back_after_interrupted_firewall_mutation(
    db_session, authorized, enabled_config, fail_with_exception
):
    device = make_device(db_session)
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    plan, _, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="block_internet"),
        config=enabled_config,
        now=NOW,
    )
    runner.fail_mutation_at = 6
    runner.fail_with_exception = fail_with_exception

    result = apply_block_internet(
        db_session,
        device.id,
        plan_id=plan.id,
        approver="tester",
        config=enabled_config,
        now=NOW,
        adapter=adapter,
    )

    assert result["status"] == "failed"
    assert result["rollback"]["status"] == "rolled_back"
    assert result["verification"]["applied"] is False
    assert runner.rules == []
    assert runner.elements == set()


def test_apply_restore_recreates_prior_rules_after_interrupted_deletion(
    db_session, authorized, enabled_config
):
    device = make_device(db_session)
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    block_plan, _, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="block_internet"),
        config=enabled_config,
        now=NOW,
    )
    assert (
        apply_block_internet(
            db_session,
            device.id,
            plan_id=block_plan.id,
            approver="tester",
            config=enabled_config,
            now=NOW,
            adapter=adapter,
        )["status"]
        == "applied"
    )
    restore_plan, _, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="restore_internet"),
        config=enabled_config,
        now=NOW,
    )
    runner.fail_mutation_at = runner.mutation_count + 2

    result = apply_restore_internet(
        db_session,
        device.id,
        plan_id=restore_plan.id,
        approver="tester",
        config=enabled_config,
        now=NOW,
        adapter=adapter,
    )

    assert result["status"] == "failed"
    assert result["rollback"]["status"] == "rolled_back"
    assert result["verification"]["verified"] is True
    assert {rule["comment"] for rule in runner.rules} == {
        "netra-device-1-egress",
        "netra-device-1-ingress",
        "netra-device-1-egress-ipv6",
        "netra-device-1-ingress-ipv6",
    }


def test_apply_rejects_missing_or_mismatched_approval(
    db_session, authorized, enabled_config
):
    device = make_device(db_session)
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)

    with pytest.raises(PlanError) as exc:
        apply_block_internet(
            db_session,
            device.id,
            plan_id=None,
            approver="tester",
            config=enabled_config,
            now=NOW,
            adapter=adapter,
        )
    assert exc.value.code == "plan_required"

    plan, _, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="block_internet"),
        config=enabled_config,
        now=NOW,
    )
    with pytest.raises(PlanError) as exc:
        apply_block_internet(
            db_session,
            device.id,
            plan_id=plan.id,
            approver="",
            config=enabled_config,
            now=NOW,
            adapter=adapter,
        )
    assert exc.value.code == "approver_required"
    assert runner.log == []

    other = make_device(db_session, ip="10.200.0.12", mac="AA:BB:CC:DD:EE:0C")
    with pytest.raises(PlanError) as exc:
        apply_block_internet(
            db_session,
            other.id,
            plan_id=plan.id,
            approver="tester",
            config=enabled_config,
            now=NOW,
            adapter=adapter,
        )
    assert exc.value.code == "plan_mismatch"


def test_apply_revalidates_identity_before_commands(
    db_session, authorized, enabled_config
):
    device = make_device(db_session)
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    plan, _, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="block_internet"),
        config=enabled_config,
        now=NOW,
    )

    observation = (
        db_session.query(DeviceObservation)
        .filter(DeviceObservation.device_id == device.id)
        .first()
    )
    observation.observed_at = NOW - timedelta(seconds=601)
    db_session.commit()

    with pytest.raises(IdentityError) as exc:
        apply_block_internet(
            db_session,
            device.id,
            plan_id=plan.id,
            approver="tester",
            config=enabled_config,
            now=NOW,
            adapter=adapter,
        )
    assert exc.value.code == "stale_observation"
    assert runner.log == []


def test_apply_restore_updates_control_state(db_session, authorized, enabled_config):
    device = make_device(db_session)
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)

    block_plan, _, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="block_internet"),
        config=enabled_config,
        now=NOW,
    )
    assert (
        apply_block_internet(
            db_session,
            device.id,
            plan_id=block_plan.id,
            approver="tester",
            config=enabled_config,
            now=NOW,
            adapter=adapter,
        )["status"]
        == "applied"
    )

    restore_plan, _, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="restore_internet"),
        config=enabled_config,
        now=NOW,
    )
    result = apply_restore_internet(
        db_session,
        device.id,
        plan_id=restore_plan.id,
        approver="tester",
        config=enabled_config,
        now=NOW,
        adapter=adapter,
    )

    assert result["status"] == "restored"
    assert result["verification"]["applied"] is False
    control = get_control_state(db_session, device.id, "internet_access")
    assert control.status == "reverted"
    assert control.nft_rule_handles_json == []
    assert db_session.query(ConfigSnapshot).count() == 2


def test_verify_internet_block_is_read_only(db_session, authorized, enabled_config):
    device = make_device(db_session)
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)

    verification = verify_internet_block(
        db_session,
        device.id,
        config=enabled_config,
        now=NOW,
        adapter=adapter,
    )

    assert verification["verified"] is False
    assert verification["device"]["device_id"] == device.id
    assert all(argv[1] == "-j" for argv in runner.log)


def test_rollback_internet_control_uses_stored_snapshot(
    db_session, authorized, enabled_config
):
    device = make_device(db_session)
    runner = FakeNftRunner()
    adapter = NftablesAdapter(enabled_config, runner)
    plan, _, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="block_internet"),
        config=enabled_config,
        now=NOW,
    )
    apply_block_internet(
        db_session,
        device.id,
        plan_id=plan.id,
        approver="tester",
        config=enabled_config,
        now=NOW,
        adapter=adapter,
    )

    result = rollback_internet_control(
        db_session,
        device.id,
        config=enabled_config,
        now=NOW,
        adapter=adapter,
    )

    assert result["status"] == "rolled_back"
    assert result["verification"]["applied"] is False
    assert (
        get_control_state(db_session, device.id, "internet_access").status
        == "rolled_back"
    )


class ForcedFailedVerifyAdapter(NftablesAdapter):
    def verify(self, target):
        result = super().verify(target)
        result["verified"] = False
        result["reasons"] = ["forced_verification_failure"]
        return result


def test_apply_rolls_back_when_verification_fails(
    db_session, authorized, enabled_config
):
    device = make_device(db_session)
    runner = FakeNftRunner()
    adapter = ForcedFailedVerifyAdapter(enabled_config, runner)
    plan, _, _ = build_dry_run_plan(
        db_session,
        NetworkControlRequest(device_id=device.id, action="block_internet"),
        config=enabled_config,
        now=NOW,
    )

    result = apply_block_internet(
        db_session,
        device.id,
        plan_id=plan.id,
        approver="tester",
        config=enabled_config,
        now=NOW,
        adapter=adapter,
    )

    assert result["status"] == "failed"
    assert result["rollback"]["status"] == "rolled_back"
    assert runner.elements == set()
    assert runner.rules == []
    assert (
        get_control_state(db_session, device.id, "internet_access").status == "failed"
    )
