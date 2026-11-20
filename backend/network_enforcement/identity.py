"""Validate a device before any network-control plan or apply operation.

Identity is deliberately stricter than the general inventory API: a target is
accepted only when the stored device, its latest observation, and the existing
discovery authorization evidence all agree.
"""

import ipaddress
from datetime import datetime, timedelta

from sqlalchemy import func

from db.models import Device, DeviceObservation
from discovery import service as discovery_service
from network_enforcement.config import INTERFACE_PATTERN, NetworkEnforcementConfig
from network_enforcement.errors import IdentityError
from network_enforcement.target import DeviceTarget, _isoformat, _naive_utc

# DeviceTarget is re-exported here for existing backend imports. New code should
# import it from network_enforcement.target so it stays independent of this
# DB-heavy module.


def _normalize_mac(value):
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if not discovery_service.MAC_ADDRESS_PATTERN.fullmatch(normalized):
        return None
    if normalized == "00:00:00:00:00:00":
        return None
    return normalized


def _validate_device_id(device_id):
    if isinstance(device_id, bool) or not isinstance(device_id, int) or device_id <= 0:
        raise IdentityError(
            "device_id must be a positive integer", code="invalid_device_id"
        )


def _validate_ip(value):
    try:
        address = ipaddress.ip_address(str(value).strip())
    except (TypeError, ValueError):
        raise IdentityError(
            "Device IP address is invalid", code="invalid_ip"
        ) from None
    if (
        address.version != 4
        or not address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
    ):
        raise IdentityError(
            "Device IP address must be a usable private IPv4 address",
            code="invalid_ip",
        )
    return address


def _validate_subnet(device, address, authorized):
    subnet_source = "device"
    raw = (device.network_subnet or "").strip()
    if raw:
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            raise IdentityError(
                "Device subnet is not valid CIDR", code="invalid_subnet"
            ) from None
        if (
            network.version != 4
            or network.prefixlen < 16
            or not discovery_service.is_private_subnet(str(network))
        ):
            raise IdentityError(
                "Device subnet must be a private IPv4 subnet no larger than /16",
                code="invalid_subnet",
            )
        if address not in network:
            raise IdentityError(
                "Device IP address is outside its recorded subnet",
                code="ip_outside_subnet",
            )
        if not any(network.subnet_of(allowed) for allowed in authorized):
            raise IdentityError(
                "Device subnet is outside the authorized LAN ranges",
                code="unauthorized_subnet",
            )
        return network, subnet_source

    candidates = [allowed for allowed in authorized if address in allowed]
    if not candidates:
        raise IdentityError(
            "Device IP address is outside the authorized LAN ranges",
            code="unauthorized_ip",
        )
    return max(candidates, key=lambda item: item.prefixlen), "authorized_network"


def _check_conflicts(db, device_id, ip_address, mac_address, cutoff):
    duplicate_device_ip = (
        db.query(Device)
        .filter(
            Device.id != device_id,
            Device.ip_address == ip_address,
            Device.is_current.is_(True),
        )
        .first()
    )
    if duplicate_device_ip is not None:
        raise IdentityError(
            "Another current device already uses this IP address", code="duplicate_ip"
        )

    duplicate_device_mac = (
        db.query(Device)
        .filter(
            Device.id != device_id,
            func.upper(Device.mac_address) == mac_address,
        )
        .first()
    )
    if duplicate_device_mac is not None:
        raise IdentityError(
            "Another device already uses this MAC address", code="duplicate_mac"
        )

    duplicate_observation_ip = (
        db.query(DeviceObservation)
        .filter(
            DeviceObservation.device_id != device_id,
            DeviceObservation.ip_address == ip_address,
            DeviceObservation.observed_at >= cutoff,
        )
        .first()
    )
    if duplicate_observation_ip is not None:
        raise IdentityError(
            "A recent observation maps this IP to another device",
            code="observation_ip_conflict",
        )

    duplicate_observation_mac = (
        db.query(DeviceObservation)
        .filter(
            DeviceObservation.device_id != device_id,
            func.upper(DeviceObservation.mac_address) == mac_address,
            DeviceObservation.observed_at >= cutoff,
        )
        .first()
    )
    if duplicate_observation_mac is not None:
        raise IdentityError(
            "A recent observation maps this MAC to another device",
            code="observation_mac_conflict",
        )


def resolve_device_target(
    db,
    device_id,
    *,
    config=None,
    now=None,
    authorized_networks=None,
    required_source_prefix=None,
):
    """Return a validated enforcement target or raise :class:`IdentityError`."""
    config = config or NetworkEnforcementConfig.from_env()
    _validate_device_id(device_id)

    if not config.interface or not INTERFACE_PATTERN.fullmatch(config.interface):
        raise IdentityError(
            "A valid Netra enforcement interface must be configured",
            code="interface_not_configured",
            details={"hint": "NETRA_NETWORK_ENFORCEMENT_INTERFACE"},
        )

    device = db.get(Device, device_id)
    if device is None:
        raise IdentityError("Device was not found", code="device_not_found")

    address = _validate_ip(device.ip_address)

    if not device.mac_address:
        raise IdentityError(
            "Device has no MAC address; stable identity cannot be verified",
            code="missing_mac",
        )
    mac_address = _normalize_mac(device.mac_address)
    if mac_address is None:
        raise IdentityError("Device MAC address is invalid", code="invalid_mac")

    if authorized_networks is None:
        try:
            authorized = discovery_service.get_authorized_networks()
        except Exception as exc:
            raise IdentityError(
                "Authorized LAN ranges could not be determined",
                code="authorization_unavailable",
            ) from exc
    else:
        authorized = list(authorized_networks)
    if not authorized:
        raise IdentityError(
            "No authorized LAN range is available", code="unauthorized_network"
        )
    if not any(address in network for network in authorized):
        raise IdentityError(
            "Device IP address is outside the authorized LAN ranges",
            code="unauthorized_ip",
        )

    network, subnet_source = _validate_subnet(device, address, authorized)

    current_time = _naive_utc(now) if now is not None else datetime.utcnow()
    cutoff = current_time - timedelta(seconds=config.observation_ttl_seconds)
    _check_conflicts(db, device_id, str(address), mac_address, cutoff)

    observation = (
        db.query(DeviceObservation)
        .filter(DeviceObservation.device_id == device_id)
        .order_by(DeviceObservation.observed_at.desc())
        .first()
    )
    if observation is None:
        raise IdentityError(
            "Device has no observation record", code="missing_observation"
        )
    if required_source_prefix and not (
        observation.source or ""
    ).startswith(required_source_prefix):
        raise IdentityError(
            "Device does not have a fresh observation from the active hotspot",
            code="hotspot_observation_required",
        )
    if required_source_prefix and not device.is_current:
        raise IdentityError(
            "Device is not currently connected to the active hotspot",
            code="device_disconnected",
        )

    observed_at = _naive_utc(observation.observed_at)
    age_seconds = (current_time - observed_at).total_seconds()
    if age_seconds > config.observation_ttl_seconds:
        raise IdentityError(
            "Device observation is too old to trust", code="stale_observation"
        )

    observation_ip = str(_validate_ip(observation.ip_address))
    if observation_ip != str(address):
        raise IdentityError(
            "Latest observation disagrees with the device IP",
            code="observation_ip_conflict",
        )

    observation_mac = _normalize_mac(observation.mac_address)
    if observation_mac and observation_mac != mac_address:
        raise IdentityError(
            "Latest observation disagrees with the device MAC",
            code="observation_mac_conflict",
        )

    if observation.network_subnet:
        try:
            observed_network = ipaddress.ip_network(
                observation.network_subnet, strict=False
            )
        except ValueError:
            raise IdentityError(
                "Latest observation has an invalid subnet",
                code="observation_subnet_conflict",
            ) from None
        if address not in observed_network:
            raise IdentityError(
                "Latest observation subnet disagrees with the device IP",
                code="observation_subnet_conflict",
            )

    evidence = {
        "ip": {
            "address": str(address),
            "subnet": str(network),
            "subnet_source": subnet_source,
            "authorized_networks": [str(item) for item in authorized],
        },
        "mac": {
            "address": mac_address,
            "observation": observation_mac,
        },
        "observation": {
            "id": observation.id,
            "observed_at": _isoformat(observed_at),
            "age_seconds": round(age_seconds, 3),
            "source": observation.source,
        },
        "device": {
            "id": device.id,
            "is_current": bool(device.is_current),
            "last_seen": _isoformat(device.last_seen),
        },
        "checks": {
            "private_ipv4": True,
            "authorized_subnet": True,
            "stable_mac": True,
            "fresh_observation": True,
            "no_ip_conflict": True,
            "no_mac_conflict": True,
        },
    }

    return DeviceTarget(
        device_id=device.id,
        ip_address=str(address),
        mac_address=mac_address,
        network_subnet=str(network),
        interface=config.interface,
        observation_id=observation.id,
        observed_at=observed_at,
        source=observation.source,
        evidence=evidence,
    )
