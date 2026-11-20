"""Safe, injectable command builders for future Netra network enforcement.

Stage 1 builds command lists and can execute them through a single audited
helper. It never decides when to execute them; firewall and qdisc adapters will
do that in later stages.
"""

import ipaddress
import re
import shlex
import subprocess
from dataclasses import dataclass

from network_enforcement.config import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    INTERFACE_PATTERN,
    TABLE_NAME_PATTERN,
)
from network_enforcement.errors import CommandError

MIN_RATE_KBPS = 1
MAX_RATE_KBPS = 10_000_000
ALLOWED_COMMANDS = frozenset({"nft", "tc", "ip"})
NFT_HANDLE_PATTERN = re.compile(r"^\d{1,12}$")
MAC_ADDRESS_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
TC_HANDLE_PATTERN = re.compile(r"^[0-9a-fA-F]{1,4}:[0-9a-fA-F]{0,4}$")
TC_CLASSID_PATTERN = re.compile(r"^[0-9a-fA-F]{1,4}:[0-9a-fA-F]{1,4}$")


@dataclass(frozen=True)
class CommandPlan:
    argv: tuple[str, ...]
    description: str

    def display(self):
        return " ".join(shlex.quote(part) for part in self.argv)

    def to_dict(self):
        return {
            "argv": list(self.argv),
            "command": self.display(),
            "description": self.description,
        }


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self):
        return self.returncode == 0

    def to_dict(self):
        return {
            "argv": list(self.argv),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "ok": self.ok,
        }


def validate_table_name(value):
    if not isinstance(value, str) or not TABLE_NAME_PATTERN.fullmatch(value):
        raise CommandError("Invalid nftables table name", code="invalid_table_name")
    return value


def validate_set_name(value):
    if not isinstance(value, str) or not TABLE_NAME_PATTERN.fullmatch(value):
        raise CommandError("Invalid nftables set name", code="invalid_set_name")
    return value


def validate_interface(value):
    if not isinstance(value, str) or not INTERFACE_PATTERN.fullmatch(value):
        raise CommandError(
            "Invalid network interface name", code="invalid_interface_name"
        )
    return value


def validate_ipv4(value):
    try:
        address = ipaddress.ip_address(str(value).strip())
    except (TypeError, ValueError):
        raise CommandError("Invalid IPv4 address", code="invalid_ip_address") from None
    if (
        address.version != 4
        or not address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
    ):
        raise CommandError(
            "Only usable private IPv4 addresses are supported",
            code="invalid_ip_address",
        )
    return str(address)


def validate_mac_address(value):
    if not isinstance(value, str) or not MAC_ADDRESS_PATTERN.fullmatch(value):
        raise CommandError("Invalid device MAC address", code="invalid_mac_address")
    normalized = value.upper()
    first_octet = int(normalized[:2], 16)
    if normalized == "00:00:00:00:00:00" or first_octet & 1:
        raise CommandError(
            "Device MAC address must be unicast", code="invalid_mac_address"
        )
    return normalized


def validate_rate_kbps(value, label="rate"):
    if isinstance(value, bool):
        raise CommandError(f"{label} must be an integer", code="invalid_rate")
    try:
        rate = int(value)
    except (TypeError, ValueError):
        raise CommandError(f"{label} must be an integer", code="invalid_rate") from None
    if not MIN_RATE_KBPS <= rate <= MAX_RATE_KBPS:
        raise CommandError(
            f"{label} must be between {MIN_RATE_KBPS} and {MAX_RATE_KBPS} kbit/s",
            code="invalid_rate",
        )
    return rate


def validate_prio(value):
    if isinstance(value, bool):
        raise CommandError("filter priority must be an integer", code="invalid_prio")
    try:
        prio = int(value)
    except (TypeError, ValueError):
        raise CommandError(
            "filter priority must be an integer", code="invalid_prio"
        ) from None
    if not 1 <= prio <= 65535:
        raise CommandError("filter priority is out of range", code="invalid_prio")
    return prio


def validate_device_id(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CommandError(
            "device_id must be a positive integer", code="invalid_device_id"
        )
    return value


def _validate_tc_handle(value):
    if not isinstance(value, str) or not TC_HANDLE_PATTERN.fullmatch(value):
        raise CommandError("Invalid tc handle", code="invalid_tc_handle")
    return value


def _validate_tc_classid(value):
    if not isinstance(value, str) or not TC_CLASSID_PATTERN.fullmatch(value):
        raise CommandError("Invalid tc classid", code="invalid_tc_classid")
    return value


def _validate_nft_handle(value):
    if isinstance(value, bool):
        raise CommandError("Invalid nftables handle", code="invalid_nft_handle")
    handle = str(value)
    if not NFT_HANDLE_PATTERN.fullmatch(handle):
        raise CommandError("Invalid nftables handle", code="invalid_nft_handle")
    return handle


def _plan(argv, description):
    return CommandPlan(tuple(str(part) for part in argv), description)


# nftables: read-only inspection


def nft_list_tables():
    return _plan(("nft", "-j", "list", "tables"), "Read nftables access readiness")


def nft_list_table(table):
    table = validate_table_name(table)
    return _plan(
        ("nft", "-j", "list", "table", "inet", table),
        "Inspect the Netra-owned nftables table",
    )


def nft_list_set(table, set_name):
    table = validate_table_name(table)
    set_name = validate_set_name(set_name)
    return _plan(
        ("nft", "-j", "list", "set", "inet", table, set_name),
        "Inspect the Netra-owned blocked-device set",
    )


def nft_list_chain(table, chain):
    table = validate_table_name(table)
    chain = validate_set_name(chain)
    return _plan(
        ("nft", "-j", "list", "chain", "inet", table, chain),
        "Inspect the Netra-owned forward chain",
    )


# nftables: staged changes (only for a verified, Netra-owned table)


def nft_add_table(table):
    table = validate_table_name(table)
    return _plan(
        (
            "nft",
            "add",
            "table",
            "inet",
            table,
            '{ comment "netra-managed" ; }',
        ),
        "Create a Netra-owned table only when no conflicting table exists",
    )


def nft_add_set(table, set_name):
    table = validate_table_name(table)
    set_name = validate_set_name(set_name)
    return _plan(
        (
            "nft",
            "add",
            "set",
            "inet",
            table,
            set_name,
            '{ type ipv4_addr ; comment "netra-managed" ; }',
        ),
        "Create the dedicated blocked-device IPv4 set",
    )


def nft_add_chain(table, chain):
    table = validate_table_name(table)
    chain = validate_set_name(chain)
    return _plan(
        (
            "nft",
            "add",
            "chain",
            "inet",
            table,
            chain,
            '{ type filter hook forward priority 10 ; policy accept ; comment "netra-managed" ; }',
        ),
        "Create a Netra-owned forward chain with an accept policy",
    )


def nft_add_element(table, set_name, ip_address):
    table = validate_table_name(table)
    set_name = validate_set_name(set_name)
    address = validate_ipv4(ip_address)
    return _plan(
        ("nft", "add", "element", "inet", table, set_name, "{", address, "}"),
        "Add one validated device IP to the Netra-owned set",
    )


def nft_delete_element(table, set_name, ip_address):
    table = validate_table_name(table)
    set_name = validate_set_name(set_name)
    address = validate_ipv4(ip_address)
    return _plan(
        ("nft", "delete", "element", "inet", table, set_name, "{", address, "}"),
        "Remove one validated device IP from the Netra-owned set",
    )


def nft_block_rules(table, chain, set_name, device_id, interface, mac_address):
    table = validate_table_name(table)
    chain = validate_set_name(chain)
    set_name = validate_set_name(set_name)
    device_id = validate_device_id(device_id)
    interface = validate_interface(interface)
    mac_address = validate_mac_address(mac_address)
    scoped_interface = f'"{interface}"'
    egress = _plan(
        (
            "nft",
            "add",
            "rule",
            "inet",
            table,
            chain,
            "iifname",
            scoped_interface,
            "ether",
            "saddr",
            mac_address,
            "ip",
            "saddr",
            f"@{set_name}",
            "drop",
            "comment",
            f'"netra-device-{device_id}-egress"',
        ),
        f"Drop forwarded packets from the validated device on {interface}",
    )
    ingress = _plan(
        (
            "nft",
            "add",
            "rule",
            "inet",
            table,
            chain,
            "oifname",
            scoped_interface,
            "ether",
            "daddr",
            mac_address,
            "ip",
            "daddr",
            f"@{set_name}",
            "drop",
            "comment",
            f'"netra-device-{device_id}-ingress"',
        ),
        f"Drop forwarded packets to the validated device on {interface}",
    )
    ipv6_egress = _plan(
        (
            "nft",
            "add",
            "rule",
            "inet",
            table,
            chain,
            "iifname",
            scoped_interface,
            "ether",
            "saddr",
            mac_address,
            "meta",
            "nfproto",
            "ipv6",
            "drop",
            "comment",
            f'"netra-device-{device_id}-egress-ipv6"',
        ),
        f"Drop forwarded IPv6 packets from the validated device on {interface}",
    )
    ipv6_ingress = _plan(
        (
            "nft",
            "add",
            "rule",
            "inet",
            table,
            chain,
            "oifname",
            scoped_interface,
            "ether",
            "daddr",
            mac_address,
            "meta",
            "nfproto",
            "ipv6",
            "drop",
            "comment",
            f'"netra-device-{device_id}-ingress-ipv6"',
        ),
        f"Drop forwarded IPv6 packets to the validated device on {interface}",
    )
    return (egress, ingress, ipv6_egress, ipv6_ingress)


def nft_delete_rule(table, chain, handle):
    table = validate_table_name(table)
    chain = validate_set_name(chain)
    handle = _validate_nft_handle(handle)
    return _plan(
        ("nft", "delete", "rule", "inet", table, chain, "handle", handle),
        "Delete one recorded Netra-owned rule by handle",
    )


# tc: read-only inspection and egress HTB builders


def tc_show_qdisc(interface):
    interface = validate_interface(interface)
    return _plan(
        ("tc", "-j", "qdisc", "show", "dev", interface),
        "Inspect existing qdiscs before any bandwidth change",
    )


def tc_show_classes(interface):
    interface = validate_interface(interface)
    return _plan(
        ("tc", "-j", "class", "show", "dev", interface),
        "Inspect existing HTB classes",
    )


def tc_add_root_htb(interface, root_handle="1:"):
    interface = validate_interface(interface)
    root_handle = _validate_tc_handle(root_handle)
    return _plan(
        (
            "tc",
            "qdisc",
            "add",
            "dev",
            interface,
            "root",
            "handle",
            root_handle,
            "htb",
            "default",
            "1",
        ),
        "Create a Netra-managed HTB root only if the root slot is empty",
    )


def tc_add_class(interface, classid, rate_kbps, *, root_handle="1:", ceil_kbps=None):
    interface = validate_interface(interface)
    classid = _validate_tc_classid(classid)
    root_handle = _validate_tc_handle(root_handle)
    rate = validate_rate_kbps(rate_kbps, "rate")
    ceil = validate_rate_kbps(ceil_kbps if ceil_kbps is not None else rate, "ceil")
    argv = [
        "tc",
        "class",
        "add",
        "dev",
        interface,
        "parent",
        root_handle,
        "classid",
        classid,
        "htb",
        "rate",
        f"{rate}kbit",
        "ceil",
        f"{ceil}kbit",
    ]
    return _plan(argv, "Add one device-specific HTB class")


def tc_add_filter(interface, ip_address, classid, *, root_handle="1:", prio=10):
    interface = validate_interface(interface)
    address = validate_ipv4(ip_address)
    classid = _validate_tc_classid(classid)
    root_handle = _validate_tc_handle(root_handle)
    prio = validate_prio(prio)
    source_hex = ipaddress.IPv4Address(address).packed.hex()
    return _plan(
        (
            "tc",
            "filter",
            "add",
            "dev",
            interface,
            "parent",
            root_handle,
            "protocol",
            "ip",
            "prio",
            str(prio),
            "u32",
            "match",
            "ip",
            "src",
            f"{source_hex}/ffffffff",
            "classid",
            classid,
        ),
        "Match one validated device IP to its HTB class",
    )


def tc_delete_filter(interface, *, root_handle="1:", prio=10):
    interface = validate_interface(interface)
    root_handle = _validate_tc_handle(root_handle)
    prio = validate_prio(prio)
    return _plan(
        (
            "tc",
            "filter",
            "del",
            "dev",
            interface,
            "parent",
            root_handle,
            "protocol",
            "ip",
            "prio",
            str(prio),
        ),
        "Delete only the Netra-owned filter priority for one device",
    )


def tc_delete_root_qdisc(interface, root_handle="1:"):
    interface = validate_interface(interface)
    root_handle = _validate_tc_handle(root_handle)
    return _plan(
        ("tc", "qdisc", "del", "dev", interface, "root", "handle", root_handle),
        "Delete a recorded Netra-owned HTB root by exact handle",
    )


def ip_show_link(name):
    name = validate_interface(name)
    return _plan(
        ("ip", "-j", "link", "show", "dev", name),
        "Inspect an existing interface without changing it",
    )


def run_command(argv, config=None):
    """Execute an allowlisted command with argument-list semantics and a timeout."""
    if isinstance(argv, str) or not isinstance(argv, (list, tuple)) or not argv:
        raise CommandError(
            "Command argv must be a non-empty sequence", code="invalid_argv"
        )
    if not all(isinstance(part, str) for part in argv):
        raise CommandError("Command arguments must be strings", code="invalid_argv")
    parts = list(argv)
    if parts[0] not in ALLOWED_COMMANDS:
        raise CommandError(
            f"Command {parts[0]!r} is not allowlisted",
            code="command_not_allowed",
            details={"allowed": sorted(ALLOWED_COMMANDS)},
        )
    if any("\x00" in part for part in parts):
        raise CommandError("Command arguments contain a null byte", code="invalid_argv")

    timeout = (
        config.command_timeout_seconds
        if config is not None
        else DEFAULT_COMMAND_TIMEOUT_SECONDS
    )
    try:
        completed = subprocess.run(
            parts,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandError(
            "Command timed out",
            code="command_timeout",
            details={"argv": parts, "timeout_seconds": timeout},
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise CommandError(
            "Command could not be executed",
            code="command_unavailable",
            details={"argv": parts, "error": str(exc)},
        ) from exc

    return CommandResult(
        tuple(parts),
        completed.returncode,
        completed.stdout or "",
        completed.stderr or "",
    )
