from discovery.service import is_authorized_router_ip


def validate_router_ip(ip):
    return is_authorized_router_ip(ip)


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
        return False

    def reachable(self):
        return self.network_reachable()

    def capabilities(self):
        return {
            "router_ip": self.ip,
            "network_reachable": self.network_reachable(),
            "management_interface_available": self.management_interface_available(),
            "reachable": self.reachable(),
            "dhcp_leases": "unsupported",
            "connected_devices": "unsupported",
            "management_protocols": [],
            "dns_logs": "unsupported",
            "authentication_required": "unknown",
        }
