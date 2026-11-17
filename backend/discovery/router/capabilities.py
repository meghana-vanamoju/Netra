CAPABILITY_FIELDS = ["management_api","dhcp_leases","connected_devices","dns_config","dns_logs","firewall","backup_restore"]

def detect_capabilities(info):
    caps = {f: "unknown" for f in CAPABILITY_FIELDS}
    # default: local discovery always available
    caps["local_discovery"] = "supported"
    return caps
