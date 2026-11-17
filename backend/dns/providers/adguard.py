import ipaddress
from urllib.parse import urlsplit

import httpx


class AdGuardHomeAdapter:
    def __init__(self, url=None, username=None, password=None, timeout=3.0):
        self.url = url.rstrip("/") if url else None
        self.username = username
        self.password = password
        self.timeout = timeout

    def available(self):
        return bool(self.url and urlsplit(self.url).scheme in {"http", "https"})

    def dhcp_status(self):
        if not self.available():
            raise RuntimeError("AdGuard Home is not configured")
        auth = (
            (self.username, self.password) if self.username and self.password else None
        )
        response = httpx.get(
            f"{self.url}/control/dhcp/status",
            auth=auth,
            timeout=self.timeout,
            follow_redirects=False,
        )
        response.raise_for_status()
        return response.json()

    def collect(self):
        status = self.dhcp_status()
        if not isinstance(status, dict):
            raise ValueError("Invalid AdGuard Home DHCP response")
        devices = []
        for lease_type, key in (("dhcp", "leases"), ("static", "static_leases")):
            leases = status.get(key, [])
            if not isinstance(leases, list):
                raise ValueError("Invalid AdGuard Home DHCP lease list")
            for lease in leases:
                if not isinstance(lease, dict):
                    continue
                ip_address = lease.get("ip")
                if not isinstance(ip_address, str):
                    continue
                try:
                    ip_address = str(ipaddress.ip_address(ip_address))
                except ValueError:
                    continue
                mac_address = lease.get("mac")
                hostname = lease.get("hostname")
                expires = lease.get("expires")
                devices.append(
                    {
                        "ip_address": ip_address,
                        "mac_address": mac_address.strip().upper()
                        if isinstance(mac_address, str) and mac_address.strip()
                        else None,
                        "hostname": hostname
                        if isinstance(hostname, str) and hostname
                        else None,
                        "vendor": None,
                        "connection_type": lease_type,
                        "online_status": "unknown",
                        "lease_expires": expires
                        if isinstance(expires, str) and expires
                        else None,
                        "last_seen": None,
                        "discovery_source": "router:adguard-home",
                    }
                )
        return devices
