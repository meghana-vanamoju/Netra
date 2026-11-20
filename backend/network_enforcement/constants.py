"""Shared names for Netra-owned network enforcement objects."""

SET_NAME = "netra_blocked_v4"
CHAIN_NAME = "netra_forward"
ROOT_HANDLE = "1:"

MODE_INTERNET_ACCESS = "internet_access"
MODE_BANDWIDTH = "bandwidth"

BACKEND_NAME = "network:nftables"
TABLE_COMMENT = "netra-managed"


def device_set_name(device_id):
    value = str(device_id)
    if not value.isdecimal() or value == "0":
        raise ValueError("device_id must be a positive decimal integer")
    name = f"netra_dev_{value}"
    if len(name) > 32:
        raise ValueError("device_id is too large for a Netra nftables set name")
    return name
