import ipaddress
import subprocess
import socket

PRIVATE_NETS = [ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("172.16.0.0/12"), ipaddress.ip_network("192.168.0.0/16")]

def is_private_subnet(cidr: str) -> bool:
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False
    return any(net.subnet_of(p) for p in PRIVATE_NETS) or net in PRIVATE_NETS

def validate_subnet(cidr: str) -> str:
    if not is_private_subnet(cidr):
        raise ValueError("Only private LAN subnets are allowed")
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
    hosts = list(net.hosts())[:max_hosts]
    for h in hosts:
        ip = str(h)
        try:
            subprocess.run(["ping", "-c", "1", "-W", str(int(timeout)), ip],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout+1)
        except Exception:
            pass
    for e in read_arp_table():
        found[e["ip"]] = e
    out = []
    for ip, e in found.items():
        if ipaddress.ip_address(ip) in net:
            out.append({
                "ip_address": ip,
                "mac_address": e.get("mac"),
                "hostname": resolve_hostname(ip),
                "discovery_source": "arp",
            })
    return out