import ipaddress, socket

def validate_router_ip(ip):
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

def arp_present(ip):
    try:
        with open("/proc/net/arp") as f:
            for line in f.readlines()[1:]:
                if line.split() and line.split()[0] == ip:
                    return True
    except FileNotFoundError:
        pass
    return False

class RouterAdapter:
    def __init__(self, ip):
        self.ip = ip
    def network_reachable(self):
        return arp_present(self.ip)
    def management_interface_available(self):
        try:
            socket.create_connection((self.ip, 80), timeout=1)
            return True
        except Exception:
            return False
    def reachable(self):
        # Backwards-compatible: network presence OR management port
        return self.network_reachable() or self.management_interface_available()
    def capabilities(self):
        return {
            "router_ip": self.ip,
            "network_reachable": self.network_reachable(),
            "management_interface_available": self.management_interface_available(),
            "reachable": self.reachable(),
            "dhcp_leases": "unsupported",
            "dns_logs": "unsupported",
            "authentication_required": "unknown",
        }