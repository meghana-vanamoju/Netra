"""Read-only detection of the active uplink, hotspot, and associated clients."""

import ipaddress
import json
import os
import re
import subprocess
import time
from pathlib import Path

from network_enforcement.config import INTERFACE_PATTERN

MAC_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
_UNUSABLE_NEIGHBOR_STATES = {"FAILED", "INCOMPLETE", "NOARP"}


def _run(argv, *, runner=None, timeout=3.0):
    execute = runner or subprocess.run
    try:
        result = execute(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    if result.returncode != 0:
        return None, (result.stderr or "").strip() or f"exit status {result.returncode}"
    return result.stdout, None


def _json_command(argv, *, runner=None):
    output, error = _run(argv, runner=runner)
    if error:
        return None, error
    try:
        value = json.loads(output or "[]")
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON output: {exc}"
    if not isinstance(value, list):
        return None, "unexpected JSON response"
    return value, None


def _nm_devices(*, runner=None):
    output, error = _run(
        [
            "nmcli",
            "--terse",
            "--escape",
            "no",
            "--fields",
            "DEVICE,TYPE,STATE,CONNECTION",
            "device",
            "status",
        ],
        runner=runner,
    )
    if error:
        return {}, error
    devices = {}
    for line in (output or "").splitlines():
        fields = line.split(":", 3)
        if len(fields) != 4 or not INTERFACE_PATTERN.fullmatch(fields[0]):
            continue
        devices[fields[0]] = {
            "type": fields[1].strip().lower(),
            "state": fields[2].strip().lower(),
            "connection": fields[3].strip() or None,
        }
    return devices, None


def _interface_address(interface, *, runner=None):
    entries, error = _json_command(
        ["ip", "-j", "-4", "addr", "show", "dev", interface], runner=runner
    )
    if error:
        return None, None
    for item in entries:
        for address in item.get("addr_info", []):
            if address.get("family") != "inet" or address.get("scope") != "global":
                continue
            try:
                subnet = ipaddress.ip_interface(
                    f"{address['local']}/{address['prefixlen']}"
                )
            except (KeyError, ValueError):
                continue
            return str(subnet.ip), str(subnet.network)
    return None, None


def _is_access_point(interface, connection, *, runner=None):
    if connection:
        output, error = _run(
            [
                "nmcli",
                "--get-values",
                "802-11-wireless.mode",
                "connection",
                "show",
                connection,
            ],
            runner=runner,
        )
        if not error:
            mode = (output or "").strip().lower()
            if mode:
                return mode == "ap"

    output, error = _run(["iw", "dev", interface, "info"], runner=runner)
    if error:
        return False
    return any(line.strip().lower() == "type ap" for line in (output or "").splitlines())


def _default_route(*, runner=None):
    routes, error = _json_command(
        ["ip", "-j", "route", "show", "default"], runner=runner
    )
    if error:
        return None, error
    candidates = [route for route in routes if route.get("dev")]
    if not candidates:
        return None, None
    route = min(candidates, key=lambda item: int(item.get("metric", 0) or 0))
    interface = route.get("dev")
    if not isinstance(interface, str) or not INTERFACE_PATTERN.fullmatch(interface):
        return None, "default route has an invalid interface name"
    return route, None


def _parse_station_dump(output):
    stations = set()
    for line in output.splitlines():
        fields = line.strip().split()
        if len(fields) >= 2 and fields[0].lower() == "station":
            mac = fields[1].upper()
            if MAC_PATTERN.fullmatch(mac) and mac != "00:00:00:00:00:00":
                stations.add(mac)
    return stations


def _parse_leases(paths, *, now=None):
    current_time = int(time.time() if now is None else now)
    leases = {}
    warnings = []
    for path in paths:
        try:
            contents = Path(path).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            continue
        except OSError as exc:
            warnings.append(f"Could not read DHCP lease file {path}: {exc}")
            continue
        for line in contents.splitlines():
            fields = line.split()
            if len(fields) < 4:
                continue
            try:
                expires = int(fields[0])
                address = ipaddress.ip_address(fields[2])
            except (ValueError, TypeError):
                continue
            mac = fields[1].upper()
            if (
                not MAC_PATTERN.fullmatch(mac)
                or mac == "00:00:00:00:00:00"
                or address.version != 4
                or not address.is_private
                or (expires != 0 and expires <= current_time)
            ):
                continue
            leases[mac] = {
                "ip_address": str(address),
                "hostname": None if fields[3] == "*" else fields[3],
            }
    return leases, warnings


def _lease_paths(interface, environ=None):
    env = environ if environ is not None else os.environ
    paths = [
        path.strip()
        for path in env.get("NETRA_DHCP_LEASE_FILES", "").split(os.pathsep)
        if path.strip()
    ]
    paths.extend(
        [
            f"/var/lib/NetworkManager/dnsmasq-{interface}.leases",
            "/var/lib/misc/dnsmasq.leases",
            "/var/lib/dnsmasq/dnsmasq.leases",
        ]
    )
    return list(dict.fromkeys(paths))


def _neighbors(interface, *, runner=None):
    entries, error = _json_command(
        ["ip", "-j", "neigh", "show", "dev", interface], runner=runner
    )
    if error:
        return {}, error
    result = {}
    for entry in entries:
        mac = str(entry.get("lladdr") or "").upper()
        states = entry.get("state") or []
        if isinstance(states, str):
            states = [states]
        if (
            not MAC_PATTERN.fullmatch(mac)
            or mac == "00:00:00:00:00:00"
            or any(str(state).upper() in _UNUSABLE_NEIGHBOR_STATES for state in states)
        ):
            continue
        try:
            address = ipaddress.ip_address(entry.get("dst", ""))
        except ValueError:
            continue
        if address.version == 4 and address.is_private:
            result[mac] = str(address)
    return result, None


def discover_hotspot_clients(
    interface,
    *,
    runner=None,
    environ=None,
    now=None,
):
    """Correlate current Wi-Fi associations with DHCP leases or neighbor entries."""
    if not isinstance(interface, str) or not INTERFACE_PATTERN.fullmatch(interface):
        return [], ["Hotspot interface is unavailable or invalid"]

    output, station_error = _run(
        ["iw", "dev", interface, "station", "dump"], runner=runner
    )
    if station_error:
        return [], [f"Wi-Fi station list is unavailable: {station_error}"]
    stations = _parse_station_dump(output or "")
    leases, warnings = _parse_leases(
        _lease_paths(interface, environ), now=now
    )
    neighbors, neighbor_error = _neighbors(interface, runner=runner)
    if neighbor_error:
        warnings.append(f"Hotspot neighbor table is unavailable: {neighbor_error}")

    clients = []
    for mac in sorted(stations):
        lease = leases.get(mac)
        neighbor_ip = neighbors.get(mac)
        conflict = bool(
            lease and neighbor_ip and lease["ip_address"] != neighbor_ip
        )
        ip_address = None if conflict else (
            lease["ip_address"] if lease else neighbor_ip
        )
        sources = ["wifi_station"]
        if lease:
            sources.append("dhcp_lease")
        if neighbor_ip:
            sources.append("neighbor_table")
        clients.append(
            {
                "ip_address": ip_address,
                "mac_address": mac,
                "hostname": lease.get("hostname") if lease else None,
                "connection_status": "connected",
                "identity_status": (
                    "conflict" if conflict else "validated" if ip_address else "required"
                ),
                "sources": sources,
            }
        )
    return clients, warnings


def detect_network_topology(*, runner=None, environ=None, now=None):
    """Return read-only uplink/hotspot facts and currently associated clients."""
    devices, nm_error = _nm_devices(runner=runner)
    route, route_error = _default_route(runner=runner)
    uplink = {
        "connected": bool(route),
        "connection_type": None,
        "interface": None,
        "ip_address": None,
        "gateway": None,
        "subnet": None,
    }
    if route:
        interface = route["dev"]
        nm_device = devices.get(interface, {})
        ip_address, subnet = _interface_address(interface, runner=runner)
        uplink.update(
            {
                "connection_type": nm_device.get("type") or "unknown",
                "interface": interface,
                "ip_address": ip_address,
                "gateway": route.get("gateway"),
                "subnet": subnet,
            }
        )

    hotspot_device = None
    for interface, device in devices.items():
        if device["type"] != "wifi" or "connected" not in device["state"]:
            continue
        if _is_access_point(
            interface, device.get("connection"), runner=runner
        ):
            hotspot_device = (interface, device)
            break

    if hotspot_device is None:
        # NetworkManager can report a Wi-Fi device as unavailable while the
        # kernel still exposes an active AP; inspect only known Wi-Fi devices.
        for interface, device in devices.items():
            if device["type"] == "wifi" and _is_access_point(
                interface, device.get("connection"), runner=runner
            ):
                hotspot_device = (interface, device)
                break

    hotspot = {
        "active": hotspot_device is not None,
        "interface": None,
        "ip_address": None,
        "subnet": None,
        "connection": None,
    }
    clients = []
    warnings = []
    if hotspot_device is not None:
        interface, device = hotspot_device
        ip_address, subnet = _interface_address(interface, runner=runner)
        hotspot.update(
            {
                "interface": interface,
                "ip_address": ip_address,
                "subnet": subnet,
                "connection": device.get("connection"),
            }
        )
        clients, client_warnings = discover_hotspot_clients(
            interface, runner=runner, environ=environ, now=now
        )
        warnings.extend(client_warnings)
    if nm_error:
        warnings.append(f"NetworkManager status is unavailable: {nm_error}")
    if route_error:
        warnings.append(f"Default route is unavailable: {route_error}")
    if route and not devices.get(route["dev"]):
        warnings.append("The default-route interface is not managed by NetworkManager")

    return {
        "uplink": uplink,
        "hotspot": hotspot,
        "connected_device_count": sum(
            1 for client in clients if client["connection_status"] == "connected"
        ),
        "clients": clients,
        "warnings": warnings,
    }
