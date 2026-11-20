import ipaddress
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import (
    Device,
    DeviceNetworkControl,
    DeviceNetworkControlEvent,
    DeviceObservation,
    DryRunPlan,
)
from db.session import get_db
from network_enforcement.config import NetworkEnforcementConfig
from network_enforcement.constants import MODE_INTERNET_ACCESS
from network_enforcement.errors import HelperError, NetworkEnforcementError
from network_enforcement.privileged_client import HelperClient
from network_enforcement.identity import resolve_device_target
from network_enforcement.service import (
    NetworkControlRequest,
    apply_block_internet,
    apply_restore_internet,
    build_dry_run_plan,
    get_control_state,
    verify_internet_block,
)
from network_enforcement.topology import detect_network_topology

router = APIRouter(tags=["network-control"])
device_router = APIRouter(prefix="/api/devices", tags=["network-control"])


class PlanRequest(BaseModel):
    action: Literal["block_internet", "restore_internet"]


class ApplyRequest(BaseModel):
    plan_id: int = Field(ge=1)
    action: Literal["block_internet", "restore_internet"]
    confirm: bool
    approver: str = Field(min_length=1, max_length=128)


def _http_error(error):
    if error.code == "device_not_found":
        status = 404
    elif error.code in {
        "device_disconnected",
        "hotspot_observation_required",
        "stale_observation",
        "observation_ip_conflict",
        "observation_mac_conflict",
        "duplicate_ip",
        "duplicate_mac",
    }:
        status = 409
    elif error.code in {"apply_not_permitted", "interface_not_configured"}:
        status = 409
    elif error.code in {
        "helper_unavailable",
        "helper_permission_denied",
        "helper_timeout",
    }:
        status = 503
    elif (
        error.code.startswith("nft")
        or error.code.startswith("command")
        or error.code.startswith("helper")
    ):
        status = 502
    else:
        status = 422
    return HTTPException(status_code=status, detail=error.to_dict())


def require_loopback_client(request: Request):
    client = request.client
    try:
        address = ipaddress.ip_address(client.host) if client else None
    except ValueError:
        address = None
    if address is None or not address.is_loopback:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "loopback_required",
                "message": "Network control changes are available only from the Netra host.",
            },
        )


def _network_context(topology=None):
    topology = topology or detect_network_topology()
    hotspot = topology.get("hotspot") or {}
    interface = hotspot.get("interface")
    subnet = hotspot.get("subnet")
    if not hotspot.get("active") or not interface or not subnet:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "hotspot_unavailable",
                "message": "An active hotspot with a detected IPv4 subnet is required.",
            },
        )
    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "invalid_hotspot_subnet",
                "message": "The active hotspot did not report a valid subnet.",
            },
        ) from None
    if network.version != 4 or not network.is_private:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "invalid_hotspot_subnet",
                "message": "Network control requires a private IPv4 hotspot subnet.",
            },
        )

    base_config = NetworkEnforcementConfig.from_env()
    if base_config.interface and base_config.interface != interface:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "hotspot_interface_mismatch",
                "message": "The configured enforcement interface differs from the active hotspot.",
                "details": {
                    "configured_interface": base_config.interface,
                    "hotspot_interface": interface,
                },
            },
        )
    config = replace(base_config, interface=interface)
    return topology, config, network, f"hotspot:{interface}"


def _effective_net_admin_status(path="/proc/self/status"):
    try:
        with open(path, encoding="ascii") as status_file:
            for line in status_file:
                if line.startswith("CapEff:"):
                    capabilities = int(line.split(":", 1)[1].strip(), 16)
                    return "present" if capabilities & (1 << 12) else "missing"
    except (OSError, ValueError):
        return "unknown"
    return "unknown"


def _helper_readiness(config):
    """Probe the restricted helper without executing nft in the backend."""
    result = {
        "status": "not_checked",
        "authorized": False,
        "nftables_available": None,
        "state": None,
        "error": None,
    }
    if not config.enabled:
        return result
    client = HelperClient(
        config.helper_socket_path, config.helper_timeout_seconds, config.table
    )
    try:
        payload = client.probe()
    except HelperError as exc:
        result["status"] = {
            "helper_unavailable": "unavailable",
            "helper_permission_denied": "permission_denied",
            "helper_timeout": "timeout",
        }.get(exc.code, "rejected")
        result["error"] = exc.to_dict()
        return result
    result["status"] = "available"
    result["authorized"] = True
    result["state"] = payload.get("state") or {}
    result["nftables_available"] = bool(payload.get("nftables_available"))
    return result


def _enforcement_status(topology, config):
    hotspot = topology.get("hotspot") or {}
    interface = hotspot.get("interface")
    matches = not config.interface or config.interface == interface
    helper = _helper_readiness(config)
    capability_status = _effective_net_admin_status()

    if not hotspot.get("active") or not interface:
        state = "hotspot_unavailable"
    elif not matches:
        state = "interface_mismatch"
    elif not config.enabled:
        state = "disabled"
    elif helper["status"] == "unavailable":
        state = "helper_unavailable"
    elif helper["status"] == "permission_denied":
        state = "helper_permission_denied"
    elif helper["status"] == "timeout":
        state = "helper_timeout"
    elif helper["status"] == "rejected":
        state = "helper_rejected"
    elif helper["status"] != "available":
        state = "helper_unavailable"
    elif config.dry_run:
        state = "dry_run"
    else:
        state = "ready"

    configuration_ready = bool(
        hotspot.get("active")
        and interface
        and matches
        and config.enabled
        and not config.dry_run
    )
    mutation_permitted = bool(
        config.enabled
        and hotspot.get("active")
        and interface
        and matches
        and helper["status"] == "available"
        and helper["authorized"]
    )
    return {
        "status": state,
        "configuration_ready": configuration_ready,
        "enabled": config.enabled,
        "dry_run": config.dry_run,
        "privilege_model": "restricted_local_helper",
        "backend_cap_net_admin": capability_status,
        "helper_status": helper["status"],
        "helper_authorized": helper["authorized"],
        "helper_socket_path": config.helper_socket_path,
        "helper_error": helper["error"],
        "nftables_binary_available": helper["nftables_available"],
        "nftables_inspection_status": "available"
        if helper["status"] == "available"
        else helper["status"],
        "nftables_write_permission_status": "helper_capability_not_write_probed"
        if helper["status"] == "available"
        else "helper_unavailable",
        "apply_permitted": config.apply_permitted and mutation_permitted,
        "mutation_permitted": mutation_permitted,
        "firewall_rules_installed": None,
        "firewall_rules_verified": None,
        "physical_connectivity_status": "not_tested",
        "physical_connectivity_confirmed": False,
        "interface": interface,
        "table": config.table,
        "warnings": list(config.warnings),
    }


def _record_event(
    db,
    *,
    device_id,
    action,
    status,
    plan_id=None,
    target_ip=None,
    interface=None,
    details=None,
):
    db.add(
        DeviceNetworkControlEvent(
            device_id=device_id,
            action=action,
            status=status,
            plan_id=plan_id,
            target_ip=target_ip,
            interface=interface,
            details_json=details or {},
        )
    )
    db.commit()


def _active_device_rows(db, topology, interface, subnet):
    now = datetime.utcnow()
    clients = list(topology.get("clients") or [])
    addresses = {}
    for client in clients:
        address = client.get("ip_address")
        if address:
            addresses.setdefault(address, []).append(client)

    by_mac = {}
    response_rows = []
    for client in clients:
        mac = (client.get("mac_address") or "").upper()
        ip_address = client.get("ip_address")
        status = client.get("identity_status", "required")
        if ip_address and len(addresses.get(ip_address, [])) > 1:
            status = "conflict"
        device = None
        if mac:
            device = (
                db.query(Device).filter(func.upper(Device.mac_address) == mac).first()
            )
        if status == "validated" and mac and ip_address:
            if device is None:
                device = Device(
                    ip_address=ip_address,
                    mac_address=mac,
                    hostname=client.get("hostname"),
                    discovery_source="networkmanager-hotspot",
                    network_subnet=subnet,
                    is_current=True,
                    last_seen=now,
                )
                db.add(device)
                db.flush()
            else:
                device.ip_address = ip_address
                device.hostname = client.get("hostname") or device.hostname
                device.discovery_source = "networkmanager-hotspot"
                device.network_subnet = subnet
                device.is_current = True
                device.last_seen = now

            last_observation = (
                db.query(DeviceObservation)
                .filter(DeviceObservation.device_id == device.id)
                .order_by(DeviceObservation.observed_at.desc())
                .first()
            )
            latest_is_fresh = (
                last_observation is not None
                and last_observation.source == f"hotspot:{interface}"
                and last_observation.ip_address == ip_address
                and last_observation.mac_address == mac
                and now - last_observation.observed_at < timedelta(seconds=15)
            )
            if not latest_is_fresh:
                db.add(
                    DeviceObservation(
                        device_id=device.id,
                        ip_address=ip_address,
                        mac_address=mac,
                        network_subnet=subnet,
                        observed_at=now,
                        source=f"hotspot:{interface}",
                    )
                )
            by_mac[mac] = device

        control = (
            get_control_state(db, device.id, MODE_INTERNET_ACCESS)
            if device is not None
            else None
        )
        response_rows.append(_device_row(device, client, control, status, interface))

    db.flush()
    known_devices = (
        db.query(Device)
        .filter(
            Device.network_subnet == subnet,
            Device.mac_address.is_not(None),
        )
        .all()
    )
    for device in known_devices:
        if device.mac_address and device.mac_address.upper() in by_mac:
            continue
        latest = (
            db.query(DeviceObservation)
            .filter(DeviceObservation.device_id == device.id)
            .order_by(DeviceObservation.observed_at.desc())
            .first()
        )
        if latest and (latest.source or "").startswith("hotspot:"):
            device.is_current = False
            control = get_control_state(db, device.id, MODE_INTERNET_ACCESS)
            if control is not None:
                response_rows.append(
                    _device_row(
                        device,
                        None,
                        control,
                        "disconnected",
                        interface,
                    )
                )

    for control in (
        db.query(DeviceNetworkControl)
        .filter(DeviceNetworkControl.mode == MODE_INTERNET_ACCESS)
        .all()
    ):
        if any(row["device_id"] == control.device_id for row in response_rows):
            continue
        device = db.get(Device, control.device_id)
        if device is not None and control.status in ("applied", "failed", "planned"):
            response_rows.append(
                _device_row(
                    device,
                    None,
                    control,
                    "disconnected",
                    interface,
                )
            )

    db.commit()
    response_rows.sort(
        key=lambda row: (
            row["connection_status"] != "connected",
            (row["name"] or row["ip_address"] or "").lower(),
        )
    )
    return response_rows


def _device_row(device, client, control, identity_status, interface):
    current_ip = (client or {}).get("ip_address")
    connection_status = (client or {}).get("connection_status") or "disconnected"
    name = (
        (client or {}).get("hostname")
        or (device.hostname if device else None)
        or "Unknown device"
    )
    if control is None:
        access = "unknown"
    elif control.status == "applied":
        if (
            connection_status == "connected"
            and control.target_ip == current_ip
            and control.interface == interface
            and identity_status == "validated"
        ):
            access = "blocked_pending_verification"
        else:
            access = "reconciliation_required"
    elif control.status in ("failed", "error"):
        access = "enforcement_error"
    elif control.status == "reverted":
        access = "unknown"
    else:
        access = "pending"
    return {
        "device_id": device.id if device else None,
        "name": name,
        "ip_address": current_ip or (device.ip_address if device else None),
        "mac_address": (client or {}).get("mac_address")
        or (device.mac_address if device else None),
        "hotspot_interface": interface,
        "network_subnet": device.network_subnet if device else None,
        "first_seen": device.first_seen.isoformat() if device else None,
        "last_seen": device.last_seen.isoformat() if device else None,
        "connection_status": connection_status,
        "internet_access": access,
        "enforcement_status": control.status if control else "not_applied",
        "identity_status": identity_status,
        "sources": (client or {}).get("sources", []),
        "enforcement_error": (
            (control.details_json or {}).get("error")
            if control and isinstance(control.details_json, dict)
            else None
        ),
    }


def _verification_access(verification):
    reasons = set(verification.get("reasons") or [])
    if verification.get("applied"):
        if verification.get("verified"):
            return "blocked", True
        return "unknown", False
    if reasons.intersection(
        {"table_conflict", "set_conflict", "unscoped_rules_present"}
    ):
        return "unknown", False
    return "allowed", True


def _firewall_evidence(verification):
    return {
        "firewall_rules_installed": bool(verification.get("applied")),
        "firewall_rules_verified": bool(verification.get("verified")),
        "physical_connectivity_status": "not_tested",
        "physical_connectivity_confirmed": False,
    }


def _read_verification(db, device_id, topology, config, authorized, source_prefix):
    target = resolve_device_target(
        db,
        device_id,
        config=config,
        authorized_networks=[authorized],
        required_source_prefix=source_prefix,
    )
    return verify_internet_block(
        db,
        device_id,
        config=config,
        authorized_networks=[authorized],
        required_source_prefix=source_prefix,
    ), target


@router.get("/api/network/status")
def network_status():
    topology = detect_network_topology()
    config = NetworkEnforcementConfig.from_env()
    return {
        **topology,
        "enforcement": _enforcement_status(topology, config),
        "access_control_authorization": "loopback_only",
        "observed_at": datetime.utcnow().isoformat(),
    }


@router.get("/api/network/devices")
def connected_devices(db: Session = Depends(get_db)):
    topology = detect_network_topology()
    hotspot = topology.get("hotspot") or {}
    interface = hotspot.get("interface")
    subnet = hotspot.get("subnet")
    if not interface or not subnet:
        controls = (
            db.query(DeviceNetworkControl)
            .filter(DeviceNetworkControl.mode == MODE_INTERNET_ACCESS)
            .filter(DeviceNetworkControl.status.in_(("applied", "failed", "planned")))
            .all()
        )
        devices = [
            _device_row(
                device,
                None,
                control,
                "disconnected",
                control.interface,
            )
            for control in controls
            if (device := db.get(Device, control.device_id)) is not None
        ]
        return {
            "devices": devices,
            "connected_device_count": topology.get("connected_device_count", 0),
            "warnings": topology.get("warnings") or [],
            "observed_at": datetime.utcnow().isoformat(),
        }
    devices = _active_device_rows(db, topology, interface, subnet)
    try:
        _, config, network, source_prefix = _network_context(topology)
    except HTTPException:
        pass
    else:
        for row in devices:
            if (
                row["connection_status"] != "connected"
                or row["identity_status"] != "validated"
                or row["device_id"] is None
            ):
                continue
            try:
                verification, _ = _read_verification(
                    db,
                    row["device_id"],
                    topology,
                    config,
                    network,
                    source_prefix,
                )
            except NetworkEnforcementError as exc:
                row["internet_access"] = "enforcement_error"
                row["enforcement_error"] = exc.to_dict()
                continue
            access, verified = _verification_access(verification)
            row["internet_access"] = access if verified else "enforcement_error"
            row.update(_firewall_evidence(verification))
            row["verification_status"] = (
                "rules_verified" if verification.get("verified") else "rules_unverified"
            )
    return {
        "devices": devices,
        "connected_device_count": topology.get("connected_device_count", 0),
        "warnings": topology.get("warnings") or [],
        "observed_at": datetime.utcnow().isoformat(),
    }


@device_router.get("/{device_id}/network-control")
def network_control_state(device_id: int, db: Session = Depends(get_db)):
    topology = detect_network_topology()
    try:
        topology, config, subnet, source_prefix = _network_context(topology)
    except HTTPException:
        record = get_control_state(db, device_id, MODE_INTERNET_ACCESS)
        device = db.get(Device, device_id)
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")
        return {
            "device_id": device_id,
            "internet_access": "reconciliation_required"
            if record and record.status == "applied"
            else "unknown",
            "verified": False,
            "network_available": False,
            "enforcement": record.status if record else "not_applied",
        }

    rows = _active_device_rows(
        db, topology, topology["hotspot"]["interface"], str(subnet)
    )
    row = next((item for item in rows if item["device_id"] == device_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if row["connection_status"] != "connected" or row["identity_status"] != "validated":
        return {
            "device_id": device_id,
            "internet_access": row["internet_access"],
            "verified": False,
            "network_available": True,
            "enforcement": row["enforcement_status"],
            "identity_status": row["identity_status"],
        }
    try:
        verification, _ = _read_verification(
            db, device_id, topology, config, subnet, source_prefix
        )
    except NetworkEnforcementError as exc:
        raise _http_error(exc)
    access, verified = _verification_access(verification)
    return {
        "device_id": device_id,
        "internet_access": access,
        "verified": verified,
        "network_available": True,
        "enforcement": row["enforcement_status"],
        "target_ip": row["ip_address"],
        "mac_address": row["mac_address"],
        "interface": topology["hotspot"]["interface"],
        "verification": verification,
        **_firewall_evidence(verification),
    }


@device_router.post("/{device_id}/network-control/plan")
def create_network_control_plan(
    device_id: int,
    payload: PlanRequest,
    request: Request,
    db: Session = Depends(get_db),
    _authorized=Depends(require_loopback_client),
):
    topology, config, subnet, source_prefix = _network_context()
    readiness = _enforcement_status(topology, config)
    can_apply = (
        readiness["apply_permitted"]
        if payload.action == "block_internet"
        else readiness["mutation_permitted"]
    )
    config_allows_action = config.apply_permitted or (
        payload.action == "restore_internet" and config.enabled
    )
    if config_allows_action and not can_apply:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "enforcement_not_ready",
                "message": "Firewall configuration or nftables access is not ready.",
                "details": readiness,
            },
        )
    rows = _active_device_rows(
        db, topology, topology["hotspot"]["interface"], str(subnet)
    )
    row = next((item for item in rows if item["device_id"] == device_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Connected device not found")
    if row["identity_status"] != "validated":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "identity_validation_required",
                "message": "A fresh, non-conflicting hotspot identity is required.",
            },
        )
    try:
        plan_record, plan, impact = build_dry_run_plan(
            db,
            NetworkControlRequest(device_id=device_id, action=payload.action),
            config=config,
            authorized_networks=[subnet],
            required_source_prefix=source_prefix,
        )
    except NetworkEnforcementError as exc:
        raise _http_error(exc)
    _record_event(
        db,
        device_id=device_id,
        action=payload.action,
        status="planned",
        plan_id=plan_record.id,
        target_ip=plan["device"]["ip_address"],
        interface=topology["hotspot"]["interface"],
        details={"impact": impact, "warnings": plan.get("warnings", [])},
    )
    return {"plan_id": plan_record.id, "plan": plan, "impact": impact}


@device_router.post("/{device_id}/network-control/apply")
def apply_network_control(
    device_id: int,
    payload: ApplyRequest,
    request: Request,
    db: Session = Depends(get_db),
    _authorized=Depends(require_loopback_client),
):
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "confirmation_required",
                "message": "Explicit confirmation is required before applying a plan.",
            },
        )
    plan_record = db.get(DryRunPlan, payload.plan_id)
    if plan_record is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "plan_not_found", "message": "Dry-run plan not found."},
        )
    plan = plan_record.plan_json if isinstance(plan_record.plan_json, dict) else {}
    planned_device = plan.get("device") or {}
    if (
        plan.get("action") != payload.action
        or planned_device.get("device_id") != device_id
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "plan_mismatch",
                "message": "The approved plan does not match this device and action.",
            },
        )

    topology, config, subnet, source_prefix = _network_context()
    rows = _active_device_rows(
        db, topology, topology["hotspot"]["interface"], str(subnet)
    )
    row = next((item for item in rows if item["device_id"] == device_id), None)
    if row is None or row["identity_status"] != "validated":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "identity_validation_required",
                "message": "The device is no longer freshly identified on the hotspot.",
            },
        )

    readiness = _enforcement_status(topology, config)
    operation = (
        apply_block_internet
        if payload.action == "block_internet"
        else apply_restore_internet
    )
    try:
        result = operation(
            db,
            device_id,
            plan_id=payload.plan_id,
            approver=payload.approver.strip(),
            config=config,
            authorized_networks=[subnet],
            required_source_prefix=source_prefix,
        )
        verification = verify_internet_block(
            db,
            device_id,
            config=config,
            authorized_networks=[subnet],
            required_source_prefix=source_prefix,
        )
    except NetworkEnforcementError as exc:
        _record_event(
            db,
            device_id=device_id,
            action=payload.action,
            status="failed",
            plan_id=payload.plan_id,
            target_ip=row["ip_address"],
            interface=topology["hotspot"]["interface"],
            details=exc.to_dict(),
        )
        raise _http_error(exc)

    access, verified = _verification_access(verification)
    desired = "blocked" if payload.action == "block_internet" else "allowed"
    confirmed = (
        verified
        and access == desired
        and result.get("status")
        in (("applied",) if desired == "blocked" else ("restored", "not_applied"))
    )
    result["verification"] = verification
    result["verified"] = confirmed
    result["internet_access"] = access if confirmed else "unknown"
    result.update(_firewall_evidence(verification))
    result["configuration_ready"] = readiness["configuration_ready"]
    event_status = "applied" if confirmed else "verification_failed"
    _record_event(
        db,
        device_id=device_id,
        action=payload.action,
        status=event_status,
        plan_id=payload.plan_id,
        target_ip=row["ip_address"],
        interface=topology["hotspot"]["interface"],
        details=result,
    )
    if not confirmed:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "verification_failed",
                "message": "The backend could not verify the requested internet-access state.",
                "details": result,
            },
        )
    return result


@device_router.post("/{device_id}/network-control/verify")
def verify_network_control(device_id: int, db: Session = Depends(get_db)):
    topology, config, subnet, source_prefix = _network_context()
    try:
        verification, target = _read_verification(
            db, device_id, topology, config, subnet, source_prefix
        )
    except NetworkEnforcementError as exc:
        raise _http_error(exc)
    access, verified = _verification_access(verification)
    return {
        "device_id": device_id,
        "internet_access": access,
        "verified": verified,
        **_firewall_evidence(verification),
        "configuration_ready": _enforcement_status(topology, config)[
            "configuration_ready"
        ],
        "target": target.to_dict(),
        "verification": verification,
    }


@device_router.get("/{device_id}/network-control/history")
def network_control_history(device_id: int, db: Session = Depends(get_db)):
    if db.get(Device, device_id) is None:
        raise HTTPException(status_code=404, detail="Device not found")
    events = (
        db.query(DeviceNetworkControlEvent)
        .filter(DeviceNetworkControlEvent.device_id == device_id)
        .order_by(DeviceNetworkControlEvent.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": item.id,
            "action": item.action,
            "status": item.status,
            "plan_id": item.plan_id,
            "target_ip": item.target_ip,
            "interface": item.interface,
            "details": item.details_json or {},
            "created_at": item.created_at.isoformat(),
        }
        for item in events
    ]
