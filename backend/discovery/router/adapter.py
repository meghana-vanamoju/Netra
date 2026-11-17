import ipaddress, socket

def validate_router_ip(ip):
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

class RouterAdapter:
    def __init__(self, ip):
        self.ip = ip
    def reachable(self):
        try:
            socket.create_connection((self.ip, 80), timeout=1)
            return True
        except Exception:
            return False
    def capabilities(self):
        return {"router_ip": self.ip, "reachable": self.reachable(), "dhcp_leases": "unsupported", "dns_logs": "unsupported"}
