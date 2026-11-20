"""Dedicated, Netra-owned nftables adapter.

The adapter never reads or modifies a global ruleset. It inspects only the
configured Netra table, refuses tables it does not own, adds only tagged rules
for validated devices, and deletes only recorded or verified Netra-owned rules.
"""

import json
from collections.abc import Callable

from network_enforcement import commands
from network_enforcement.config import NetworkEnforcementConfig
from network_enforcement.constants import (
    BACKEND_NAME,
    CHAIN_NAME,
    SET_NAME,
    TABLE_COMMENT,
    device_set_name,
)
from network_enforcement.errors import CommandError, NftablesError
from network_enforcement.target import DeviceTarget

_MISSING_MESSAGES = ("no such file", "does not exist", "not found")


def _entries(payload):
    if not isinstance(payload, dict):
        return []
    values = payload.get("nftables") or []
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, dict)]


def _find(payload, key):
    for entry in _entries(payload):
        value = entry.get(key)
        if isinstance(value, dict):
            return value
    return None


def _all(payload, key):
    return [
        entry[key] for entry in _entries(payload) if isinstance(entry.get(key), dict)
    ]


def _as_int(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rule_comments(device_id, table, interface, mac_address):
    set_name = device_set_name(device_id)
    commands_by_comment = dict(
        zip(
            (
                f"netra-device-{device_id}-egress",
                f"netra-device-{device_id}-ingress",
                f"netra-device-{device_id}-egress-ipv6",
                f"netra-device-{device_id}-ingress-ipv6",
            ),
            commands.nft_block_rules(
                table, CHAIN_NAME, set_name, device_id, interface, mac_address
            ),
        )
    )
    return commands_by_comment


def _single_key(value, key):
    return isinstance(value, dict) and set(value) == {key}


def _match_statement(statement, op="=="):
    if not _single_key(statement, "match"):
        return False
    match = statement["match"]
    return (
        isinstance(match, dict)
        and set(match) == {"op", "left", "right"}
        and match["op"] == op
    )


def _meta_interface(value):
    if not _single_key(value, "meta"):
        return None
    meta = value["meta"]
    if not isinstance(meta, dict) or set(meta) != {"key"}:
        return None
    return meta["key"]


def _ipv4_payload_field(value):
    if not _single_key(value, "payload"):
        return None
    payload = value["payload"]
    if not isinstance(payload, dict) or set(payload) != {"protocol", "field"}:
        return None
    if payload["protocol"] != "ip":
        return None
    return payload["field"]


def _ether_payload_field(value):
    if not _single_key(value, "payload"):
        return None
    payload = value["payload"]
    if not isinstance(payload, dict) or set(payload) != {"protocol", "field"}:
        return None
    if payload["protocol"] != "ether":
        return None
    return payload["field"]


def _set_reference(value, set_name):
    """nftables JSON encodes a named set reference as the string ``@name``."""
    return value == f"@{set_name}"


def _rule_scope(rule, comment, interface, set_name=None, mac_address=None):
    """Structurally validate a device rule's interface, MAC, and address set."""
    comment = str(comment or "")
    ipv6_egress = comment.endswith("-egress-ipv6")
    ipv6_ingress = comment.endswith("-ingress-ipv6")
    egress = comment.endswith("-egress") or ipv6_egress
    ingress = comment.endswith("-ingress") or ipv6_ingress
    if not (egress or ingress):
        return True
    if not interface:
        return True

    expr = rule.get("expr")
    if not isinstance(expr, list) or len(expr) != 4:
        return False

    direction, mac_field = ("iifname", "saddr") if egress else ("oifname", "daddr")
    interface_match, mac_match, protocol_match, verdict = expr

    if not _match_statement(interface_match):
        return False
    if _meta_interface(interface_match["match"]["left"]) != direction:
        return False
    if interface_match["match"]["right"] != interface:
        return False

    if not _match_statement(mac_match):
        return False
    if _ether_payload_field(mac_match["match"]["left"]) != mac_field:
        return False
    actual_mac = mac_match["match"]["right"]
    if not isinstance(actual_mac, str):
        return False
    try:
        actual_mac = commands.validate_mac_address(actual_mac)
    except CommandError:
        return False
    if mac_address and actual_mac != mac_address:
        return False

    if not _match_statement(protocol_match):
        return False
    if ipv6_egress or ipv6_ingress:
        if (
            _meta_interface(protocol_match["match"]["left"]) != "nfproto"
            or protocol_match["match"]["right"] != "ipv6"
        ):
            return False
    else:
        field = "saddr" if egress else "daddr"
        if _ipv4_payload_field(protocol_match["match"]["left"]) != field:
            return False
        try:
            device_id = int(comment.split("-", 3)[2])
            expected_set = set_name or device_set_name(device_id)
        except (IndexError, ValueError):
            return False
        if not _set_reference(protocol_match["match"]["right"], expected_set):
            return False

    return verdict == {"drop": None}


def _device_rules(payload, device_id, interface=None, mac_address=None):
    set_name = device_set_name(device_id)
    expected = {
        f"netra-device-{device_id}-egress",
        f"netra-device-{device_id}-ingress",
        f"netra-device-{device_id}-egress-ipv6",
        f"netra-device-{device_id}-ingress-ipv6",
    }
    rules = []
    for rule in _all(payload, "rule"):
        comment = rule.get("comment")
        if comment not in expected or rule.get("chain") != CHAIN_NAME:
            continue
        handle = _as_int(rule.get("handle"))
        if handle is None:
            raise NftablesError(
                "Netra-owned rule has no usable handle",
                code="rule_handle_missing",
                details={"comment": comment},
            )
        rules.append(
            {
                "comment": comment,
                "handle": handle,
                "table": rule.get("table"),
                "chain": rule.get("chain"),
                "expr": rule.get("expr") or [],
                "scoped": _rule_scope(rule, comment, interface, set_name, mac_address),
            }
        )
    return rules


class NftablesAdapter:
    """Mutate only Netra-owned nftables objects with explicit opt-in."""

    def __init__(
        self,
        config: NetworkEnforcementConfig | None = None,
        runner: Callable | None = None,
    ):
        self.config = config or NetworkEnforcementConfig.from_env()
        self.runner = runner or (lambda argv, cfg: commands.run_command(argv, cfg))

    def _require_apply_permitted(self):
        if not self.config.apply_permitted:
            raise NftablesError(
                "Network enforcement apply is not permitted",
                code="apply_not_permitted",
                details={
                    "enabled": self.config.enabled,
                    "dry_run": self.config.dry_run,
                },
            )

    def _require_mutation_permitted(self):
        """Removal and rollback stay available while dry-run is still enabled."""
        if not self.config.enabled:
            raise NftablesError(
                "Network enforcement is disabled",
                code="apply_not_permitted",
                details={
                    "enabled": False,
                    "dry_run": self.config.dry_run,
                },
            )

    def _require_interface(self):
        if not self.config.interface:
            raise NftablesError(
                "A Netra enforcement interface must be configured",
                code="interface_not_configured",
            )

    def _run(self, plan, *, allow_failure=False):
        result = self.runner(plan.argv, self.config)
        ok = bool(getattr(result, "ok", False))
        if not ok and not allow_failure:
            raise NftablesError(
                "nftables command failed",
                code="nft_command_failed",
                details={
                    "command": plan.display(),
                    "returncode": getattr(result, "returncode", None),
                    "stderr": getattr(result, "stderr", ""),
                },
            )
        return result

    def _parse_json(self, result):
        stdout = (getattr(result, "stdout", "") or "").strip()
        if not stdout:
            return {"nftables": []}
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise NftablesError(
                "nftables JSON output could not be parsed",
                code="invalid_json",
                details={"error": str(exc)},
            ) from exc
        if not isinstance(payload, dict):
            raise NftablesError(
                "nftables JSON output has an unexpected shape",
                code="invalid_json",
            )
        return payload

    def _list(self, plan):
        result = self._run(plan, allow_failure=True)
        stderr = (getattr(result, "stderr", "") or "").lower()
        if bool(getattr(result, "ok", False)):
            return self._parse_json(result)
        if any(message in stderr for message in _MISSING_MESSAGES):
            return None
        raise NftablesError(
            "nftables inspection failed",
            code="inspection_failed",
            details={
                "command": plan.display(),
                "returncode": getattr(result, "returncode", None),
                "stderr": getattr(result, "stderr", ""),
            },
        )

    def state_summary(self):
        """Read-only summary used by the privileged helper readiness probe."""
        return {"table": self.inspect_table(), "chain": self._read_chain()}

    def inspect_table(self):
        payload = self._list(commands.nft_list_table(self.config.table))
        table = _find(payload, "table")
        if (
            table is None
            or table.get("family") != "inet"
            or table.get("name") != self.config.table
        ):
            return {"present": False, "owned": False, "handle": None, "comment": None}
        comment = table.get("comment")
        owned = isinstance(comment, str) and comment.lower() == TABLE_COMMENT.lower()
        return {
            "present": True,
            "owned": owned,
            "handle": _as_int(table.get("handle")),
            "comment": comment,
        }

    def ensure_table(self):
        state = self.inspect_table()
        if state["present"]:
            if not state["owned"]:
                raise NftablesError(
                    "Configured nftables table is not Netra-owned",
                    code="table_conflict",
                    details={"table": self.config.table},
                )
            return state
        self._run(commands.nft_add_table(self.config.table))
        state = self.inspect_table()
        if not state["present"] or not state["owned"]:
            raise NftablesError(
                "Netra-owned table could not be verified after creation",
                code="table_creation_failed",
                details={"table": self.config.table},
            )
        return state

    def _read_set(self, set_name=SET_NAME):
        payload = self._list(commands.nft_list_set(self.config.table, set_name))
        obj = _find(payload, "set")
        if obj is None:
            return {
                "present": False,
                "owned": False,
                "elements": [],
                "handle": None,
                "name": set_name,
            }
        comment = obj.get("comment")
        owned = (
            isinstance(comment, str)
            and comment.lower() == TABLE_COMMENT.lower()
            and obj.get("family") == "inet"
            and obj.get("table") == self.config.table
            and obj.get("name") == set_name
            and obj.get("type") == "ipv4_addr"
        )
        elements = obj.get("elem") or []
        if not isinstance(elements, list):
            elements = []
        return {
            "present": True,
            "owned": owned,
            "elements": [str(item) for item in elements],
            "handle": _as_int(obj.get("handle")),
            "name": set_name,
        }

    def ensure_set(self, set_name=SET_NAME):
        self.ensure_table()
        state = self._read_set(set_name)
        if state["present"]:
            if not state["owned"]:
                raise NftablesError(
                    "Configured nftables set is not Netra-owned",
                    code="set_conflict",
                    details={"set": set_name},
                )
            return state
        self._run(commands.nft_add_set(self.config.table, set_name))
        state = self._read_set(set_name)
        if not state["present"] or not state["owned"]:
            raise NftablesError(
                "Netra-owned set could not be verified after creation",
                code="set_creation_failed",
                details={"set": set_name},
            )
        return state

    def _read_chain_payload(self):
        return self._list(commands.nft_list_chain(self.config.table, CHAIN_NAME))

    def _read_chain(self):
        payload = self._read_chain_payload()
        chain = _find(payload, "chain")
        if chain is None:
            return {
                "present": False,
                "owned": False,
                "family": None,
                "table": None,
                "name": None,
                "type": None,
                "hook": None,
                "priority": None,
                "policy": None,
                "handle": None,
            }
        comment = chain.get("comment")
        owned = isinstance(comment, str) and comment.lower() == TABLE_COMMENT.lower()
        return {
            "present": True,
            "owned": owned,
            "family": chain.get("family"),
            "table": chain.get("table"),
            "name": chain.get("name"),
            "type": chain.get("type"),
            "hook": chain.get("hook"),
            "priority": _as_int(chain.get("prio")),
            "policy": chain.get("policy"),
            "handle": _as_int(chain.get("handle")),
        }

    def _chain_configuration_valid(self, state):
        return (
            state["family"] == "inet"
            and state["table"] == self.config.table
            and state["name"] == CHAIN_NAME
            and state["type"] == "filter"
            and state["hook"] == "forward"
            and state["priority"] == 10
            and state["policy"] == "accept"
        )

    def ensure_chain(self):
        self.ensure_table()
        state = self._read_chain()
        if state["present"]:
            if not state["owned"]:
                raise NftablesError(
                    "Configured nftables chain is not Netra-owned",
                    code="chain_conflict",
                    details={"chain": CHAIN_NAME},
                )
            if state["policy"] not in (None, "accept"):
                raise NftablesError(
                    "Netra-owned chain policy is not accept",
                    code="chain_policy_conflict",
                    details={"policy": state["policy"]},
                )
            if not self._chain_configuration_valid(state):
                raise NftablesError(
                    "Netra-owned chain has an unexpected forwarding configuration",
                    code="chain_configuration_conflict",
                    details={
                        key: state[key]
                        for key in (
                            "family",
                            "table",
                            "name",
                            "type",
                            "hook",
                            "priority",
                            "policy",
                        )
                    },
                )
            return state
        self._run(commands.nft_add_chain(self.config.table, CHAIN_NAME))
        state = self._read_chain()
        if (
            not state["present"]
            or not state["owned"]
            or not self._chain_configuration_valid(state)
        ):
            raise NftablesError(
                "Netra-owned chain could not be verified after creation",
                code="chain_creation_failed",
                details={
                    "chain": CHAIN_NAME,
                    **{
                        key: state[key]
                        for key in (
                            "family",
                            "table",
                            "name",
                            "type",
                            "hook",
                            "priority",
                            "policy",
                        )
                    },
                },
            )
        return state

    def block(self, target: DeviceTarget):
        """Add one validated device to the Netra block set and rules."""
        self._require_apply_permitted()
        self._require_interface()
        executed = []
        set_name = device_set_name(target.device_id)
        self.ensure_set(set_name)
        self.ensure_chain()

        existing = {
            rule["comment"]: rule
            for rule in _device_rules(
                self._read_chain_payload(),
                target.device_id,
                self.config.interface,
                target.mac_address,
            )
        }
        builders = _rule_comments(
            target.device_id,
            self.config.table,
            self.config.interface,
            target.mac_address,
        )
        for comment, builder in builders.items():
            rule = existing.get(comment)
            if rule is not None and not rule["scoped"]:
                raise NftablesError(
                    "Existing Netra rule is not scoped to the configured interface",
                    code="unscoped_rule_conflict",
                    details={
                        "comment": comment,
                        "handle": rule["handle"],
                        "interface": self.config.interface,
                    },
                )

        set_state = self._read_set(set_name)
        if target.ip_address not in set_state["elements"]:
            plan = commands.nft_add_element(
                self.config.table, set_name, target.ip_address
            )
            self._run(plan)
            executed.append(plan.display())

        for comment, builder in builders.items():
            if comment in existing:
                continue
            self._run(builder)
            executed.append(builder.display())

        final_set = self._read_set(set_name)
        final_rules = _device_rules(
            self._read_chain_payload(),
            target.device_id,
            self.config.interface,
            target.mac_address,
        )
        handles = [rule["handle"] for rule in final_rules]
        ip_present = target.ip_address in final_set["elements"]
        if (
            not ip_present
            or len(final_rules) != len(builders)
            or not all(rule["scoped"] for rule in final_rules)
        ):
            raise NftablesError(
                "Blocking state could not be observed after apply",
                code="block_verification_failed",
                details={
                    "device_id": target.device_id,
                    "ip_present": ip_present,
                    "rule_count": len(final_rules),
                    "interface": self.config.interface,
                },
            )

        return {
            "status": "applied",
            "device_id": target.device_id,
            "ip_address": target.ip_address,
            "table": self.config.table,
            "set": set_name,
            "chain": CHAIN_NAME,
            "interface": self.config.interface,
            "rule_handles": handles,
            "rules": final_rules,
            "executed": executed,
        }

    def restore(self, target: DeviceTarget, *, handles=None):
        """Remove only this device's Netra-owned rules and set element."""
        self._require_mutation_permitted()
        executed = []
        set_name = device_set_name(target.device_id)
        table = self.inspect_table()
        if not table["present"]:
            return {
                "status": "not_applied",
                "device_id": target.device_id,
                "ip_address": target.ip_address,
                "deleted_handles": [],
                "executed": [],
            }
        if not table["owned"]:
            raise NftablesError(
                "Configured nftables table is not Netra-owned",
                code="table_conflict",
                details={"table": self.config.table},
            )

        chain_state = self._read_chain()
        if chain_state["present"] and (
            not chain_state["owned"] or not self._chain_configuration_valid(chain_state)
        ):
            raise NftablesError(
                "Configured forward chain is not a valid Netra-owned chain",
                code="chain_configuration_conflict",
                details={"chain": CHAIN_NAME, "state": chain_state},
            )

        rules = _device_rules(
            self._read_chain_payload(),
            target.device_id,
            self.config.interface,
            target.mac_address,
        )
        if handles is not None:
            requested = set()
            for handle in handles:
                value = _as_int(handle)
                if value is None:
                    raise NftablesError(
                        "Recorded rule handle is invalid",
                        code="invalid_rule_handle",
                    )
                requested.add(value)
            known = {rule["handle"]: rule for rule in rules}
            unexpected = requested.difference(known)
            if unexpected:
                raise NftablesError(
                    "Recorded handle is not a Netra-owned rule for this device",
                    code="unexpected_rule_handle",
                    details={"handles": sorted(unexpected)},
                )
            rules = [known[handle] for handle in requested]

        for rule in rules:
            plan = commands.nft_delete_rule(
                self.config.table, CHAIN_NAME, rule["handle"]
            )
            self._run(plan)
            executed.append(plan.display())

        set_state = self._read_set(set_name)
        if set_state["present"] and not set_state["owned"]:
            raise NftablesError(
                "Configured nftables set is not Netra-owned",
                code="set_conflict",
                details={"set": set_name},
            )
        for ip_address in set_state["elements"]:
            plan = commands.nft_delete_element(self.config.table, set_name, ip_address)
            self._run(plan)
            executed.append(plan.display())

        final_set = self._read_set(set_name)
        final_rules = _device_rules(
            self._read_chain_payload(),
            target.device_id,
            self.config.interface,
            target.mac_address,
        )
        if final_rules or final_set["elements"]:
            raise NftablesError(
                "Restriction removal could not be observed",
                code="restore_verification_failed",
                details={
                    "device_id": target.device_id,
                    "elements": final_set["elements"],
                    "rule_count": len(final_rules),
                },
            )

        return {
            "status": "restored" if executed else "not_applied",
            "device_id": target.device_id,
            "ip_address": target.ip_address,
            "interface": self.config.interface,
            "deleted_handles": [rule["handle"] for rule in rules],
            "executed": executed,
        }

    def verify(self, target: DeviceTarget):
        """Read-only verification of a device's Netra-owned blocking state."""
        self._require_interface()
        table = self.inspect_table()
        if not table["present"]:
            return {
                "verified": False,
                "applied": False,
                "reasons": ["table_absent"],
                "ip_present": False,
                "interface": self.config.interface,
                "rules": [],
                "handles": [],
            }
        if not table["owned"]:
            return {
                "verified": False,
                "applied": False,
                "reasons": ["table_conflict"],
                "ip_present": False,
                "interface": self.config.interface,
                "rules": [],
                "handles": [],
            }

        chain_state = self._read_chain()
        set_name = device_set_name(target.device_id)
        set_state = self._read_set(set_name)
        if set_state["present"] and not set_state["owned"]:
            return {
                "verified": False,
                "applied": False,
                "reasons": ["set_conflict"],
                "ip_present": False,
                "interface": self.config.interface,
                "rules": [],
                "handles": [],
            }
        rules = _device_rules(
            self._read_chain_payload(),
            target.device_id,
            self.config.interface,
            target.mac_address,
        )
        scoped_rules = [rule for rule in rules if rule["scoped"]]
        unscoped_rules = [rule for rule in rules if not rule["scoped"]]
        ip_present = target.ip_address in set_state["elements"]
        found_comments = {rule["comment"] for rule in scoped_rules}
        expected = set(
            _rule_comments(
                target.device_id,
                self.config.table,
                self.config.interface,
                target.mac_address,
            )
        )
        missing = sorted(expected.difference(found_comments))
        reasons = []
        if not chain_state["present"]:
            reasons.append("chain_absent")
        elif not chain_state["owned"]:
            reasons.append("chain_conflict")
        elif not self._chain_configuration_valid(chain_state):
            reasons.append("chain_configuration_mismatch")
        if not ip_present:
            reasons.append("ip_absent_from_set")
        if missing:
            reasons.append("rules_missing")
        if unscoped_rules:
            reasons.append("unscoped_rules_present")
        return {
            "verified": not reasons,
            "applied": bool(ip_present or rules),
            "reasons": reasons,
            "ip_present": ip_present,
            "interface": self.config.interface,
            "chain": chain_state,
            "rules": rules,
            "handles": [rule["handle"] for rule in rules],
        }

    def snapshot(self, target: DeviceTarget | None = None):
        """Capture only Netra-owned state; never a global ruleset snapshot."""
        set_name = device_set_name(target.device_id) if target else SET_NAME
        table = self.inspect_table()
        if not table["present"]:
            return {
                "backend": BACKEND_NAME,
                "table_present": False,
                "owned": False,
                "interface": self.config.interface,
                "table": self.config.table,
                "device_id": target.device_id if target else None,
                "mac_address": target.mac_address if target else None,
                "elements": [],
                "rules": [],
            }
        if not table["owned"]:
            raise NftablesError(
                "Configured nftables table is not Netra-owned",
                code="table_conflict",
                details={"table": self.config.table},
            )
        set_state = self._read_set(set_name)
        chain_state = self._read_chain()
        rules = []
        for rule in _all(self._read_chain_payload(), "rule"):
            if (
                rule.get("chain") != CHAIN_NAME
                or rule.get("table") != self.config.table
            ):
                continue
            comment = rule.get("comment")
            if target and comment not in {
                f"netra-device-{target.device_id}-egress",
                f"netra-device-{target.device_id}-ingress",
                f"netra-device-{target.device_id}-egress-ipv6",
                f"netra-device-{target.device_id}-ingress-ipv6",
            }:
                continue
            handle = _as_int(rule.get("handle"))
            if handle is None:
                continue
            rules.append(
                {
                    "comment": comment,
                    "handle": handle,
                    "scoped": _rule_scope(
                        rule,
                        comment,
                        self.config.interface,
                        set_name,
                        target.mac_address if target else None,
                    ),
                }
            )
        return {
            "backend": BACKEND_NAME,
            "table_present": True,
            "owned": True,
            "interface": self.config.interface,
            "table": self.config.table,
            "device_id": target.device_id if target else None,
            "mac_address": target.mac_address if target else None,
            "target_ip": target.ip_address if target else None,
            "set_name": set_name,
            "table_handle": table["handle"],
            "set_present": set_state["present"],
            "set_owned": set_state["owned"],
            "elements": sorted(set_state["elements"]),
            "chain_present": chain_state["present"],
            "chain_owned": chain_state["owned"],
            "chain_family": chain_state["family"],
            "chain_table": chain_state["table"],
            "chain_name": chain_state["name"],
            "chain_type": chain_state["type"],
            "chain_hook": chain_state["hook"],
            "chain_priority": chain_state["priority"],
            "chain_policy": chain_state["policy"],
            "rules": rules,
        }

    def rollback(self, previous, target: DeviceTarget):
        """Restore only the target's prior state from a Netra-owned snapshot."""
        self._require_mutation_permitted()
        if not isinstance(previous, dict) or previous.get("backend") != BACKEND_NAME:
            raise NftablesError(
                "Snapshot is not a Netra nftables snapshot",
                code="invalid_snapshot",
            )
        if previous.get("table_present") and not previous.get("owned"):
            raise NftablesError(
                "Snapshot references a table that is not Netra-owned",
                code="table_conflict",
            )
        table = self.inspect_table()
        if table["present"] and not table["owned"]:
            raise NftablesError(
                "Configured nftables table is not Netra-owned",
                code="table_conflict",
                details={"table": self.config.table},
            )
        snapshot_table = previous.get("table")
        if snapshot_table and snapshot_table != self.config.table:
            raise NftablesError(
                "Snapshot table differs from the configured table",
                code="snapshot_table_mismatch",
                details={
                    "snapshot_table": snapshot_table,
                    "configured_table": self.config.table,
                },
            )
        if previous.get("device_id") not in (None, target.device_id):
            raise NftablesError(
                "Snapshot belongs to a different device",
                code="snapshot_target_mismatch",
            )
        if previous.get("mac_address") not in (None, target.mac_address):
            raise NftablesError(
                "Snapshot MAC does not match the target device",
                code="snapshot_target_mismatch",
            )
        prior_interface = previous.get("interface")
        if prior_interface and prior_interface != self.config.interface:
            raise NftablesError(
                "Snapshot interface differs from the configured interface",
                code="snapshot_interface_mismatch",
                details={
                    "snapshot_interface": prior_interface,
                    "configured_interface": self.config.interface,
                },
            )

        expected_set_name = device_set_name(target.device_id)
        set_name = previous.get("set_name") or expected_set_name
        if set_name != expected_set_name:
            raise NftablesError(
                "Snapshot set does not belong to the target device",
                code="snapshot_target_mismatch",
            )
        prior_ip = previous.get("target_ip")
        if prior_ip and prior_ip != target.ip_address:
            raise NftablesError(
                "Snapshot IP does not match the target device",
                code="snapshot_target_mismatch",
            )

        prior_elements = {
            str(item) for item in (previous.get("elements") or []) if item is not None
        }
        for ip_address in prior_elements:
            try:
                commands.validate_ipv4(ip_address)
            except CommandError as exc:
                raise NftablesError(
                    "Snapshot contains an invalid IPv4 set element",
                    code="invalid_snapshot",
                    details={"error": exc.to_dict()},
                ) from exc
        prior_handles = {}
        expected_comments = {
            f"netra-device-{target.device_id}-egress",
            f"netra-device-{target.device_id}-ingress",
            f"netra-device-{target.device_id}-egress-ipv6",
            f"netra-device-{target.device_id}-ingress-ipv6",
        }
        for rule in previous.get("rules") or []:
            if not isinstance(rule, dict):
                continue
            comment = rule.get("comment")
            handle = _as_int(rule.get("handle"))
            if comment and handle is not None:
                if comment not in expected_comments:
                    raise NftablesError(
                        "Snapshot rule does not belong to the target device",
                        code="snapshot_target_mismatch",
                        details={"comment": comment},
                    )
                prior_handles[comment] = {
                    "handle": handle,
                    "scoped": bool(rule.get("scoped", True)),
                }
        if any(not rule["scoped"] for rule in prior_handles.values()):
            raise NftablesError(
                "Snapshot contains a rule that is not safely scoped",
                code="snapshot_unscoped_rule",
            )

        executed = []
        chain_state = self._read_chain()
        if chain_state["present"] and (
            not chain_state["owned"] or not self._chain_configuration_valid(chain_state)
        ):
            raise NftablesError(
                "Configured forward chain is not a valid Netra-owned chain",
                code="chain_configuration_conflict",
                details={"chain": CHAIN_NAME, "state": chain_state},
            )
        set_state = self._read_set(set_name)
        if set_state["present"] and not set_state["owned"]:
            raise NftablesError(
                "Configured nftables set is not Netra-owned",
                code="set_conflict",
                details={"set": set_name},
            )
        if previous.get("set_present") and not set_state["present"]:
            self.ensure_set(set_name)
            set_state = self._read_set(set_name)

        current_rules = _device_rules(
            self._read_chain_payload(),
            target.device_id,
            self.config.interface,
            target.mac_address,
        )
        for rule in current_rules:
            prior = prior_handles.get(rule["comment"])
            if prior and prior["handle"] == rule["handle"]:
                if not rule["scoped"]:
                    raise NftablesError(
                        "Prior Netra rule no longer matches its recorded scope",
                        code="rollback_verification_failed",
                        details={"comment": rule["comment"]},
                    )
                continue
            plan = commands.nft_delete_rule(
                self.config.table, CHAIN_NAME, rule["handle"]
            )
            self._run(plan)
            executed.append(plan.display())

        current_elements = set(set_state["elements"])
        for ip_address in current_elements - prior_elements:
            plan = commands.nft_delete_element(self.config.table, set_name, ip_address)
            self._run(plan)
            executed.append(plan.display())

        for ip_address in prior_elements - current_elements:
            plan = commands.nft_add_element(self.config.table, set_name, ip_address)
            self._run(plan)
            executed.append(plan.display())

        missing_rule_comments = set(prior_handles)
        for rule in _device_rules(
            self._read_chain_payload(),
            target.device_id,
            self.config.interface,
            target.mac_address,
        ):
            if rule["comment"] in prior_handles and rule["scoped"]:
                missing_rule_comments.discard(rule["comment"])

        if missing_rule_comments:
            if not previous.get("chain_present"):
                raise NftablesError(
                    "Snapshot rules cannot be restored without the prior chain",
                    code="snapshot_chain_missing",
                )
            self.ensure_chain()
            builders = _rule_comments(
                target.device_id,
                self.config.table,
                self.config.interface,
                target.mac_address,
            )
            for comment in sorted(missing_rule_comments):
                builder = builders.get(comment)
                if builder is None:
                    raise NftablesError(
                        "Snapshot contains an unsupported Netra rule",
                        code="snapshot_rule_unsupported",
                        details={"comment": comment},
                    )
                self._run(builder)
                executed.append(builder.display())

        final_set = self._read_set(set_name)
        final_rules = _device_rules(
            self._read_chain_payload(),
            target.device_id,
            self.config.interface,
            target.mac_address,
        )
        elements_match = set(final_set["elements"]) == prior_elements
        expected_rules = {comment for comment in prior_handles}
        rules_match = {
            rule["comment"] for rule in final_rules if rule["scoped"]
        } == expected_rules and all(rule["scoped"] for rule in final_rules)
        if not elements_match or not rules_match:
            raise NftablesError(
                "Rollback state could not be verified",
                code="rollback_verification_failed",
                details={
                    "elements_match": elements_match,
                    "rules_match": rules_match,
                },
            )

        return {
            "status": "rolled_back" if executed else "no_change",
            "device_id": target.device_id,
            "ip_address": target.ip_address,
            "executed": executed,
        }
