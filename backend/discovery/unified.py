import ipaddress
from datetime import datetime

from sqlalchemy import func

from db.models import Device, DeviceObservation


def merge_devices(existing, new):
    out = []
    for d in existing + new:
        match = None
        for o in out:
            same_mac = (
                d.get("mac_address")
                and d.get("mac_address", "").upper()
                == (o.get("mac_address") or "").upper()
            )
            same_ip_without_conflicting_macs = (
                d.get("ip_address")
                and d.get("ip_address") == o.get("ip_address")
                and not (d.get("mac_address") and o.get("mac_address"))
            )
            if same_mac or same_ip_without_conflicting_macs:
                match = o
                break
        if match:
            for key, value in d.items():
                if value is not None and (
                    match.get(key) is None
                    or (key == "ip_address" and d.get("mac_address"))
                ):
                    match[key] = value
            sources = d.get("sources") or [d.get("discovery_source")]
            for source in sources:
                if source and source not in match.setdefault("sources", []):
                    match["sources"].append(source)
        else:
            d = dict(d)
            d["sources"] = d.get("sources") or (
                [d["discovery_source"]] if d.get("discovery_source") else []
            )
            out.append(d)
    return out


def upsert_inventory(
    db, records, *, network_subnet=None, scan_status=None, scan_partial=False
):
    now = datetime.utcnow()
    for record in records:
        ip_address = record.get("ip_address")
        if not ip_address:
            continue
        mac_address = record.get("mac_address")
        if mac_address:
            mac_address = mac_address.strip().upper()
        query = db.query(Device)
        device = (
            query.filter(func.upper(Device.mac_address) == mac_address).first()
            if mac_address
            else None
        )
        if not device:
            same_ip = query.filter(Device.ip_address == ip_address)
            if mac_address:
                same_ip = same_ip.filter(Device.mac_address.is_(None))
            device = same_ip.first()

        source = record.get("discovery_source")
        metadata = dict(device.extra or {}) if device else {}
        sources = list(metadata.get("sources", []))
        if device and not sources and device.discovery_source:
            sources.append(device.discovery_source)
        if source and source not in sources:
            sources.append(source)
        for key in ("connection_type", "online_status", "lease_expires", "last_seen"):
            if record.get(key) is not None:
                metadata[key] = record[key]
        metadata["sources"] = sources

        if device:
            device.ip_address = ip_address
            if mac_address:
                device.mac_address = mac_address
            for field in ("hostname", "vendor"):
                if record.get(field) is not None:
                    setattr(device, field, record[field])
            device.discovery_source = ",".join(sources)[:64] or source
            device.extra = metadata
            device.last_seen = now
            if network_subnet:
                device.is_current = True
                device.network_subnet = network_subnet
                device.last_scan_at = now
                device.scan_status = "partial" if scan_partial else "complete"
        else:
            db.add(
                Device(
                    ip_address=ip_address,
                    mac_address=mac_address,
                    hostname=record.get("hostname"),
                    vendor=record.get("vendor"),
                    discovery_source=source,
                    first_seen=now,
                    last_seen=now,
                    extra=metadata,
                    is_current=bool(network_subnet),
                    network_subnet=network_subnet,
                    last_scan_at=now if network_subnet else None,
                    scan_status=("partial" if scan_partial else "complete")
                    if network_subnet
                    else None,
                )
            )
            db.flush()
            device = (
                db.query(Device)
                .filter(func.upper(Device.mac_address) == mac_address)
                .first()
                if mac_address
                else db.query(Device)
                .filter(Device.ip_address == ip_address)
                .order_by(Device.id.desc())
                .first()
            )
        if (network_subnet or source) and device:
            db.add(
                DeviceObservation(
                    device_id=device.id,
                    ip_address=ip_address,
                    mac_address=mac_address,
                    network_subnet=network_subnet,
                    observed_at=now,
                    source=source,
                )
            )
    db.commit()


def replace_discovery_snapshot(
    db,
    subnet,
    records,
    *,
    scan_partial=False,
    probed_addresses=None,
    coverage_complete=None,
):
    """Replace the current snapshot for one subnet without deleting history."""
    now = datetime.utcnow()
    if probed_addresses is None:
        probed = None
        coverage = True if coverage_complete is None else bool(coverage_complete)
    else:
        probed = {str(address) for address in probed_addresses}
        if coverage_complete is None:
            try:
                network = ipaddress.ip_network(subnet, strict=False)
                total_hosts = len(list(network.hosts()))
            except ValueError:
                total_hosts = 0
            coverage = total_hosts > 0 and len(probed) >= total_hosts
        else:
            coverage = bool(coverage_complete)

    upsert_inventory(
        db,
        records,
        network_subnet=subnet,
        scan_status="partial" if (scan_partial or not coverage) else "complete",
        scan_partial=scan_partial or not coverage,
    )

    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        db.commit()
        return

    observed_ips = {
        record.get("ip_address") for record in records if record.get("ip_address")
    }
    observed_macs = {
        record.get("mac_address", "").strip().upper()
        for record in records
        if record.get("mac_address")
    }
    for device in db.query(Device).all():
        try:
            in_subnet = ipaddress.ip_address(device.ip_address) in network
        except ValueError:
            in_subnet = False
        if not in_subnet:
            continue
        observed = device.ip_address in observed_ips or (
            device.mac_address and device.mac_address.upper() in observed_macs
        )
        if observed:
            device.is_current = True
            device.network_subnet = subnet
            device.last_scan_at = now
            device.scan_status = (
                "partial" if (scan_partial or not coverage) else "complete"
            )
            metadata = dict(device.extra or {})
            metadata["scan_completeness"] = (
                "partial" if (scan_partial or not coverage) else "complete"
            )
            metadata["coverage_complete"] = coverage
            device.extra = metadata
        elif probed is not None and device.ip_address not in probed:
            metadata = dict(device.extra or {})
            metadata["scan_completeness"] = "not_probed"
            metadata["coverage_complete"] = coverage
            metadata["last_scan_subnet"] = subnet
            device.extra = metadata
        elif scan_partial or not coverage:
            metadata = dict(device.extra or {})
            metadata["partial_scan_subnet"] = subnet
            metadata["scan_completeness"] = "partial"
            metadata["coverage_complete"] = coverage
            metadata["last_scan_at"] = now.isoformat()
            device.extra = metadata
        else:
            device.is_current = False
            device.network_subnet = None
            metadata = dict(device.extra or {})
            metadata["current_snapshot"] = "not_observed"
            metadata["last_scan_subnet"] = subnet
            metadata["scan_completeness"] = "complete"
            metadata["coverage_complete"] = True
            device.extra = metadata
    db.commit()
