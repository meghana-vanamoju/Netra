import ipaddress
import os
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, wait
from itertools import islice
from time import monotonic

MAX_HOSTS_PER_SCAN = 64
MAX_PROBE_WORKERS = 8
MAX_DNS_WORKERS = 4
DEFAULT_SCAN_TIMEOUT = 12.0
MAC_ADDRESS_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class DiscoveryUnavailableError(RuntimeError):
    pass


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
        with open("/proc/net/arp", encoding="ascii", errors="ignore") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) < 6 or parts[2].lower() != "0x2":
                    continue
                try:
                    address = ipaddress.ip_address(parts[0])
                except ValueError:
                    continue
                mac = parts[3]
                if (
                    address.version == 4
                    and MAC_ADDRESS_PATTERN.fullmatch(mac)
                    and mac.upper() != "00:00:00:00:00:00"
                ):
                    results.append({"ip": str(address), "mac": mac.upper()})
    except OSError:
        pass
    return results


def resolve_hostname(ip: str, timeout: float = 0.25) -> str | None:
    try:
        result = subprocess.run(
            ["getent", "hosts", ip],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    fields = result.stdout.split()
    return fields[1] if len(fields) > 1 and fields[1] != ip else None


def _probe_host(ip: str, timeout: float) -> tuple[bool, bool, bool]:
    try:
        result = subprocess.run(
            ["ping", "-n", "-c", "1", "-W", str(max(1, int(timeout))), ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 0.25,
            check=False,
        )
        return result.returncode == 0, result.returncode == 1, result.returncode > 1
    except subprocess.TimeoutExpired:
        return False, True, False
    except (OSError, subprocess.SubprocessError):
        return False, False, True


def discover_subnet(
    cidr: str,
    timeout: float = 1.0,
    max_hosts: int = MAX_HOSTS_PER_SCAN,
    *,
    overall_timeout: float = DEFAULT_SCAN_TIMEOUT,
    workers: int = MAX_PROBE_WORKERS,
    resolve_hostnames: bool = False,
    reverse_dns_timeout: float = 0.25,
    metrics: dict | None = None,
) -> list[dict]:
    validate_subnet(cidr)
    net = ipaddress.ip_network(cidr, strict=False)
    initial_neighbors = {entry["ip"]: entry for entry in read_arp_table()}
    addresses = [
        str(address)
        for address in islice(
            net.hosts(), max(0, min(int(max_hosts), MAX_HOSTS_PER_SCAN))
        )
    ]
    host_timeout = max(0.1, float(timeout))
    scan_deadline = monotonic() + max(0.1, float(overall_timeout))
    probe_count = min(max(1, int(workers)), MAX_PROBE_WORKERS, len(addresses))
    probe_futures = {}
    completed_results = {}
    cancelled_count = 0
    overall_deadline_hit = False
    pending = set()

    if addresses:
        executor = ThreadPoolExecutor(max_workers=probe_count)
        probe_futures = {
            executor.submit(_probe_host, address, host_timeout): address
            for address in addresses
        }
        completed, pending = wait(
            probe_futures,
            timeout=max(0.0, scan_deadline - monotonic()),
        )
        overall_deadline_hit = bool(pending)
        for future in completed:
            completed_results[probe_futures[future]] = future.result()
        for future in pending:
            if future.cancel():
                cancelled_count += 1
        executor.shutdown(wait=False, cancel_futures=True)

    responders = {
        address for address, (responded, _, _) in completed_results.items() if responded
    }
    deadline_timeout_count = max(0, len(pending) - cancelled_count)
    timeout_count = (
        sum(result[1] for result in completed_results.values()) + deadline_timeout_count
    )
    probe_errors = sum(result[2] for result in completed_results.values())
    probes_attempted = len(probe_futures) - cancelled_count
    current_neighbors = {entry["ip"]: entry for entry in read_arp_table()}
    newly_observed_neighbors = {
        ip: entry
        for ip, entry in current_neighbors.items()
        if entry != initial_neighbors.get(ip)
    }
    observed_ips = responders | {
        ip for ip in newly_observed_neighbors if ipaddress.ip_address(ip) in net
    }
    out = []
    for ip in sorted(observed_ips, key=ipaddress.ip_address):
        neighbor = current_neighbors.get(ip)
        mac_address = neighbor.get("mac") if neighbor else None
        out.append(
            {
                "ip_address": ip,
                "mac_address": mac_address,
                "hostname": None,
                "discovery_source": "arp" if mac_address else "lan-discovery",
            }
        )

    if resolve_hostnames and out:
        remaining = max(0.0, scan_deadline - monotonic())
        dns_executor = ThreadPoolExecutor(max_workers=min(MAX_DNS_WORKERS, len(out)))
        dns_futures = (
            {
                dns_executor.submit(
                    resolve_hostname,
                    record["ip_address"],
                    min(max(0.01, reverse_dns_timeout), remaining),
                ): record
                for record in out
            }
            if remaining > 0
            else {}
        )
        dns_completed, dns_pending = wait(dns_futures, timeout=remaining)
        for future in dns_completed:
            try:
                dns_futures[future]["hostname"] = future.result()
            except (OSError, subprocess.SubprocessError):
                pass
        for future in dns_pending:
            future.cancel()
        dns_executor.shutdown(wait=False, cancel_futures=True)

    if metrics is not None:
        metrics.update(
            {
                "probes_attempted": probes_attempted,
                "hosts_responding": len(responders),
                "timeout_count": timeout_count,
                "probe_errors": probe_errors,
                "partial_results": (
                    overall_deadline_hit
                    or cancelled_count > 0
                    or timeout_count > 0
                    or probe_errors > 0
                ),
            }
        )

    if probes_attempted and probe_errors == probes_attempted:
        raise DiscoveryUnavailableError("No LAN probes could be started")
    return out
