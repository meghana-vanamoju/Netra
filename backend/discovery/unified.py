from datetime import datetime

from sqlalchemy import func

from db.models import Device


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


def upsert_inventory(db, records):
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
                )
            )
    db.commit()
