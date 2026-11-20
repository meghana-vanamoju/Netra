"""Lightweight device-target value object shared by backend and helper.

This module intentionally depends only on the Python standard library. It must
not import SQLAlchemy, backend database models, discovery services, or any
other FastAPI/backend-only stack: the privileged helper imports it directly.
"""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class DeviceTarget:
    device_id: int
    ip_address: str
    mac_address: str
    network_subnet: str
    interface: str
    observation_id: int | None
    observed_at: datetime | None
    source: str | None
    evidence: dict

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "network_subnet": self.network_subnet,
            "interface": self.interface,
            "observation_id": self.observation_id,
            "observed_at": _isoformat(self.observed_at),
            "source": self.source,
            "evidence": self.evidence,
        }


def _naive_utc(value):
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _isoformat(value):
    normalized = _naive_utc(value)
    return normalized.isoformat() if normalized is not None else None
