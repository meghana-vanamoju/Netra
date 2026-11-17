import ipaddress
import os
from itertools import islice
import json
import subprocess
import socket

PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]


def get_local_network_info() -> dict:
    info = {"interface": None, "ip_address": None, "gateway": None, "subnet": None}
    try:
        routes = json.loads(
            subprocess.run(
                ["ip", "-j", "route", "show", "default"],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            ).stdout
        )
        route = next((item for item in routes if item.get("dev")), None)
        if not route:
            return info
        info["interface"] = route["dev"]
        info["gateway"] = route.get("gateway")
        addresses = json.loads(
            subprocess.run(
                ["ip", "-j", "-4", "addr", "show", "dev", route["dev"]],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            ).stdout
        )
        for address in addresses:
            for entry in address.get("addr_info", []):
                if entry.get("family") == "inet" and entry.get("scope") == "global":
                    interface = ipaddress.ip_interface(
                        f"{entry['local']}/{entry['prefixlen']}"
                    )
                    info["ip_address"] = str(interface.ip)
                    info["subnet"] = str(interface.network)
                    return info
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return info
    return info


def is_private_subnet(cidr: str) -> bool:
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False
    return any(net.subnet_of(p) for p in PRIVATE_NETS) or net in PRIVATE_NETS


def get_authorized_networks() -> list[ipaddress.IPv4Network]:
    networks = []
    local_subnet = get_local_network_info().get("subnet")
    candidates = [local_subnet] if local_subnet else []
    candidates.extend(os.environ.get("NETRA_AUTHORIZED_CIDRS", "").split(","))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            network = ipaddress.ip_network(candidate.strip(), strict=False)
        except ValueError:
            continue
        if network.version == 4 and any(
            network.subnet_of(private) for private in PRIVATE_NETS
        ):
            if network not in networks:
                networks.append(network)
    return networks


def is_authorized_router_ip(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return address.version == 4 and any(
        address in network for network in get_authorized_networks()
    )


def validate_subnet(cidr: str) -> str:
    if "/" not in cidr:
        raise ValueError("Subnet must be in CIDR notation with a prefix length")
    if not is_private_subnet(cidr):
        raise ValueError("Only private LAN subnets are allowed")
    net = ipaddress.ip_network(cidr, strict=False)
    if net.version != 4 or net.prefixlen < 16:
        raise ValueError(
            "LAN discovery is limited to private IPv4 subnets no larger than /16"
        )
    if not any(net.subnet_of(authorized) for authorized in get_authorized_networks()):
        raise ValueError(
            "LAN subnet must be on the active network or in NETRA_AUTHORIZED_CIDRS"
        )
    return cidr


def read_arp_table() -> list[dict]:
    results = []
    try:
        with open("/proc/net/arp") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) >= 4:
                    ip, mac = parts[0], parts[3]
                    if mac and mac != "00:00:00:00:00:00":
                        results.append({"ip": ip, "mac": mac.upper()})
    except FileNotFoundError:
        pass
    return results


def resolve_hostname(ip: str) -> str | None:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


def discover_subnet(cidr: str, timeout: float = 1.0, max_hosts: int = 64) -> list[dict]:
    validate_subnet(cidr)
    net = ipaddress.ip_network(cidr, strict=False)
    found = {e["ip"]: e for e in read_arp_table()}
    hosts = islice(net.hosts(), max_hosts)
    for h in hosts:
        ip = str(h)
        try:
            subprocess.run(
                ["ping", "-c", "1", "-W", str(int(timeout)), ip],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout + 1,
            )
        except Exception:
            pass
    for e in read_arp_table():
        found[e["ip"]] = e
    out = []
    for ip, e in found.items():
        if ipaddress.ip_address(ip) in net:
            out.append(
                {
                    "ip_address": ip,
                    "mac_address": e.get("mac"),
                    "hostname": resolve_hostname(ip),
                    "discovery_source": "arp",
                }
            )
    return out
