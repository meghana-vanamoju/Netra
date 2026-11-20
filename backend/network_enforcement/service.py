"""Dry-run planning, apply orchestration, and additive state persistence.

Plans are created after revalidating device identity. Apply functions accept an
injected adapter, require an approved plan and opt-in configuration, and always
snapshot Netra-owned state before making a change.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from db.models import ConfigSnapshot, DeviceNetworkControl, DryRunPlan
from network_enforcement import commands
from network_enforcement.config import NetworkEnforcementConfig
from network_enforcement.constants import (
    BACKEND_NAME,
    CHAIN_NAME,
    MODE_BANDWIDTH,
    MODE_INTERNET_ACCESS,
    ROOT_HANDLE,
    device_set_name,
)
from network_enforcement.errors import (
    CommandError,
    IdentityError,
    NftablesError,
    PlanError,
)
from network_enforcement.identity import resolve_device_target
from network_enforcement.target import DeviceTarget
from network_enforcement.nftables import NftablesAdapter
from network_enforcement.privileged_client import HelperNftablesAdapter

ACTION_MODES = {
    "block_internet": (MODE_INTERNET_ACCESS,),
    "restore_internet": (MODE_INTERNET_ACCESS,),
    "set_bandwidth": (MODE_BANDWIDTH,),
    "remove_restrictions": (MODE_INTERNET_ACCESS, MODE_BANDWIDTH),
}


@dataclass(frozen=True)
class NetworkControlRequest:
    device_id: int
    action: str
    upload_kbps: int | None = None
    download_kbps: int | None = None


def _validate_request(request):
    if not isinstance(request, NetworkControlRequest):
        raise PlanError(
            "request must be a NetworkControlRequest", code="invalid_request"
        )
    if isinstance(request.device_id, bool) or not isinstance(request.device_id, int):
        raise PlanError("device_id must be an integer", code="invalid_device_id")
    action = str(request.action or "").strip()
    if action not in ACTION_MODES:
        raise PlanError(
            f"Unsupported network control action: {action}", code="unsupported_action"
        )

    upload = request.upload_kbps
    download = request.download_kbps
    if action == "set_bandwidth":
        if upload is None and download is None:
            raise PlanError(
                "set_bandwidth requires upload_kbps, download_kbps, or both",
                code="missing_rate",
            )
        try:
            if upload is not None:
                upload = commands.validate_rate_kbps(upload, "upload_kbps")
            if download is not None:
                download = commands.validate_rate_kbps(download, "download_kbps")
        except CommandError as exc:
            raise PlanError(exc.message, code=exc.code) from exc
    elif upload is not None or download is not None:
        raise PlanError(
            "Rate limits are only valid for set_bandwidth", code="unexpected_rate"
        )
    return action, upload, download


def _classid_for(device_id):
    if device_id > 0xFFFF:
        raise PlanError(
            "device_id is too large for a deterministic tc classid",
            code="device_id_out_of_range",
        )
    return f"1:{device_id:x}"


def _prio_for(device_id):
    return 10 + (device_id % 1000)


def get_control_state(db: Session, device_id, mode):
    return (
        db.query(DeviceNetworkControl)
        .filter(
            DeviceNetworkControl.device_id == device_id,
            DeviceNetworkControl.mode == mode,
        )
        .first()
    )


def _recorded_rule_handles(db, device_id):
    record = get_control_state(db, device_id, MODE_INTERNET_ACCESS)
    if record is None:
        return []
    handles = []
    if isinstance(record.nft_rule_handles_json, list):
        handles.extend(record.nft_rule_handles_json)
    if isinstance(record.details_json, dict):
        handles.extend(record.details_json.get("nft_rule_handles") or [])
    cleaned = []
    for handle in handles:
        if isinstance(handle, bool):
            continue
        try:
            value = int(handle)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in cleaned:
            cleaned.append(value)
    return cleaned


def _commands_for_action(db, action, upload, download, target, config):
    command_plans = []
    warnings = list(config.warnings)
    target_set = device_set_name(target.device_id)
    state = {
        "modes": list(ACTION_MODES[action]),
        "nft_table": config.table,
        "nft_set": target_set,
        "nft_chain": CHAIN_NAME,
        "nft_interface": config.interface,
    }

    if MODE_INTERNET_ACCESS in ACTION_MODES[action]:
        command_plans.append(commands.nft_list_table(config.table))
        if action == "block_internet":
            command_plans.extend(
                [
                    commands.nft_add_table(config.table),
                    commands.nft_add_set(config.table, target_set),
                    commands.nft_add_chain(config.table, CHAIN_NAME),
                    commands.nft_add_element(
                        config.table, target_set, target.ip_address
                    ),
                ]
            )
            command_plans.extend(
                commands.nft_block_rules(
                    config.table,
                    CHAIN_NAME,
                    target_set,
                    target.device_id,
                    config.interface,
                    target.mac_address,
                )
            )
        else:
            command_plans.append(commands.nft_list_set(config.table, target_set))
            handles = _recorded_rule_handles(db, target.device_id)
            state["recorded_rule_handles"] = handles
            for handle in handles:
                command_plans.append(
                    commands.nft_delete_rule(config.table, CHAIN_NAME, handle)
                )
            if action in ("restore_internet", "remove_restrictions") and not handles:
                warnings.append(
                    "No persisted Netra rule handles were found; apply must resolve "
                    "them from verified Netra-owned state and delete no unrelated rules."
                )
            command_plans.append(
                commands.nft_delete_element(config.table, target_set, target.ip_address)
            )

    if MODE_BANDWIDTH in ACTION_MODES[action]:
        classid = _classid_for(target.device_id)
        prio = _prio_for(target.device_id)
        state.update(
            {
                "tc_root_handle": ROOT_HANDLE,
                "tc_classid": classid,
                "tc_filter_prio": prio,
                "upload_kbps": upload,
                "download_kbps": download,
            }
        )
        command_plans.append(commands.tc_show_qdisc(config.interface))
        if action == "set_bandwidth":
            command_plans.append(
                commands.tc_add_root_htb(config.interface, ROOT_HANDLE)
            )
            if upload is not None:
                command_plans.append(
                    commands.tc_add_class(
                        config.interface,
                        classid,
                        upload,
                        root_handle=ROOT_HANDLE,
                    )
                )
                command_plans.append(
                    commands.tc_add_filter(
                        config.interface,
                        target.ip_address,
                        classid,
                        root_handle=ROOT_HANDLE,
                        prio=prio,
                    )
                )
            if download is not None:
                warnings.append(
                    "Ingress IFB download limits are a separate capability; no "
                    "ingress qdisc or interface change is planned."
                )
        else:
            command_plans.append(
                commands.tc_delete_filter(
                    config.interface, root_handle=ROOT_HANDLE, prio=prio
                )
            )
            warnings.append(
                "The HTB root qdisc is not deleted automatically because it may "
                "carry other device classes."
            )

    return command_plans, warnings, state


def _adapter_for_config(config):
    """Return the adapter that may affect live firewall state.

    The backend process stays unprivileged; when enforcement is enabled all
    nftables effects are delegated to the restricted local helper.
    """
    if config.helper_required:
        return HelperNftablesAdapter(config)
    return NftablesAdapter(config)


def _apply_blockers(config, action=None):
    blockers = []
    if not config.enabled:
        blockers.append("NETRA_NETWORK_ENFORCEMENT_ENABLED is not true")
    if config.dry_run and action != "restore_internet":
        blockers.append("NETRA_NETWORK_ENFORCEMENT_DRY_RUN is true")
    return blockers


def _sync_planned_controls(db, target, action, state, plan_id):
    """Create planned rows without downgrading any existing applied state."""
    modes = ACTION_MODES[action]
    if action == "remove_restrictions":
        return []

    records = []
    for mode in modes:
        existing = get_control_state(db, target.device_id, mode)
        if existing is not None:
            continue
        record = DeviceNetworkControl(
            device_id=target.device_id,
            mode=mode,
            action=action,
            status="planned",
            target_ip=target.ip_address,
            mac_address=target.mac_address,
            network_subnet=target.network_subnet,
            interface=target.interface,
            nft_table=state.get("nft_table"),
            nft_set=state.get("nft_set") if mode == MODE_INTERNET_ACCESS else None,
            nft_chain=state.get("nft_chain") if mode == MODE_INTERNET_ACCESS else None,
            tc_root_handle=state.get("tc_root_handle")
            if mode == MODE_BANDWIDTH
            else None,
            tc_classid=state.get("tc_classid") if mode == MODE_BANDWIDTH else None,
            upload_kbps=state.get("upload_kbps") if mode == MODE_BANDWIDTH else None,
            download_kbps=state.get("download_kbps")
            if mode == MODE_BANDWIDTH
            else None,
            dry_run_plan_id=plan_id,
            details_json={"planned_only": True, "state": state},
        )
        db.add(record)
        records.append(record)
    return records


def _require_apply_permitted(config):
    blockers = _apply_blockers(config)
    if blockers:
        raise PlanError(
            "Network enforcement apply is not permitted",
            code="apply_not_permitted",
            details={"blockers": blockers},
        )


def _require_mutation_permitted(config):
    """Removal and rollback remain available while dry-run is enabled."""
    if not config.enabled:
        raise PlanError(
            "Network enforcement is disabled",
            code="apply_not_permitted",
            details={"dry_run": config.dry_run},
        )


def _validate_approval(db, plan_id, approver, device_id, expected_action):
    if not approver or not str(approver).strip():
        raise PlanError(
            "An approver is required before apply", code="approver_required"
        )
    if plan_id is None:
        raise PlanError("An approved dry-run plan is required", code="plan_required")
    plan = db.get(DryRunPlan, plan_id)
    if plan is None:
        raise PlanError("Dry-run plan was not found", code="plan_not_found")
    payload = plan.plan_json if isinstance(plan.plan_json, dict) else {}
    if payload.get("action") != expected_action:
        raise PlanError(
            "Dry-run plan action does not match the requested apply",
            code="plan_mismatch",
        )
    device = payload.get("device") or {}
    try:
        planned_device_id = int(device.get("device_id"))
    except (TypeError, ValueError):
        raise PlanError(
            "Dry-run plan has no valid device", code="plan_mismatch"
        ) from None
    if planned_device_id != device_id:
        raise PlanError("Dry-run plan targets a different device", code="plan_mismatch")
    return plan


def _snapshot_checksum(state):
    raw = json.dumps(state, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _create_snapshot(db, state, policy_id=None):
    snapshot = ConfigSnapshot(
        backend=BACKEND_NAME,
        state_json=state,
        checksum=_snapshot_checksum(state),
        policy_id=policy_id,
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def _snapshot_state(snapshot):
    if snapshot is None:
        raise PlanError("Config snapshot was not found", code="snapshot_not_found")
    state = snapshot.state_json
    if not isinstance(state, dict):
        raise PlanError("Config snapshot has no state", code="invalid_snapshot")
    if snapshot.checksum and snapshot.checksum != _snapshot_checksum(state):
        raise PlanError(
            "Config snapshot checksum does not match its state",
            code="snapshot_integrity_failed",
        )
    return state


def _upsert_control(db, target, status, result, snapshot, verification):
    record = get_control_state(db, target.device_id, MODE_INTERNET_ACCESS)
    if record is None:
        record = DeviceNetworkControl(
            device_id=target.device_id,
            mode=MODE_INTERNET_ACCESS,
        )
    consent = result.get("consent") or {}
    record.action = result.get("action", record.action or "block_internet")
    record.status = status
    record.target_ip = target.ip_address
    record.mac_address = target.mac_address
    record.network_subnet = target.network_subnet
    record.interface = target.interface
    record.nft_table = result.get("table")
    record.nft_set = result.get("set") or device_set_name(target.device_id)
    record.nft_chain = CHAIN_NAME
    record.nft_rule_handles_json = (
        result.get("rule_handles") or verification.get("handles") or []
    )
    record.snapshot_id = snapshot.id if snapshot is not None else None
    record.dry_run_plan_id = consent.get("plan_id")
    record.policy_id = result.get("policy_id")
    record.details_json = {
        "verification": verification,
        "executed": result.get("executed") or result.get("deleted_handles") or [],
        "rolled_back": bool(result.get("rollback")),
    }
    db.add(record)
    return record


def _attempt_rollback(adapter, previous, target):
    try:
        return adapter.rollback(previous, target)
    except (NftablesError, CommandError) as error:
        return {"status": "failed", "error": error.to_dict()}


def _attempt_verification(adapter, target):
    try:
        return adapter.verify(target)
    except (NftablesError, CommandError) as error:
        return {
            "verified": False,
            "applied": True,
            "reasons": ["verification_error"],
            "error": error.to_dict(),
        }


def apply_block_internet(
    db: Session,
    device_id: int,
    *,
    plan_id: int,
    approver: str,
    config: NetworkEnforcementConfig | None = None,
    now=None,
    adapter: NftablesAdapter | None = None,
    policy_id: int | None = None,
    authorized_networks=None,
    required_source_prefix=None,
):
    """Apply a previously planned internet block after revalidating identity."""
    config = config or NetworkEnforcementConfig.from_env()
    _require_apply_permitted(config)
    _validate_approval(db, plan_id, approver, device_id, "block_internet")
    target = resolve_device_target(
        db,
        device_id,
        config=config,
        now=now,
        authorized_networks=authorized_networks,
        required_source_prefix=required_source_prefix,
    )
    adapter = adapter or _adapter_for_config(config)

    previous = adapter.snapshot(target)
    snapshot = _create_snapshot(db, previous, policy_id)
    consent = {"approver": str(approver).strip(), "plan_id": plan_id}

    try:
        result = adapter.block(target)
        result["action"] = "block_internet"
    except (NftablesError, CommandError) as exc:
        rollback = _attempt_rollback(adapter, previous, target)
        result = {
            "status": "failed",
            "action": "block_internet",
            "error": exc.to_dict(),
            "rollback": rollback,
        }

    verification = _attempt_verification(adapter, target)
    result["verification"] = verification
    result["snapshot_id"] = snapshot.id
    result["consent"] = consent
    result["device"] = target.to_dict()
    if policy_id is not None:
        result["policy_id"] = policy_id

    success = result["status"] == "applied" and verification["verified"]
    if not success:
        if "rollback" not in result:
            result["rollback"] = _attempt_rollback(adapter, previous, target)
            verification = _attempt_verification(adapter, target)
            result["verification"] = verification
        result["status"] = "failed"
    result["verification_after_rollback" if not success else "verification"] = (
        verification
    )

    record_status = "applied" if success else "failed"
    _upsert_control(db, target, record_status, result, snapshot, verification)
    db.commit()
    return result


def apply_restore_internet(
    db: Session,
    device_id: int,
    *,
    plan_id: int,
    approver: str,
    config: NetworkEnforcementConfig | None = None,
    now=None,
    adapter: NftablesAdapter | None = None,
    policy_id: int | None = None,
    authorized_networks=None,
    required_source_prefix=None,
):
    """Remove only this device's Netra-owned internet restriction."""
    config = config or NetworkEnforcementConfig.from_env()
    _require_mutation_permitted(config)
    _validate_approval(db, plan_id, approver, device_id, "restore_internet")
    target = resolve_device_target(
        db,
        device_id,
        config=config,
        now=now,
        authorized_networks=authorized_networks,
        required_source_prefix=required_source_prefix,
    )
    adapter = adapter or _adapter_for_config(config)

    previous = adapter.snapshot(target)
    snapshot = _create_snapshot(db, previous, policy_id)
    consent = {"approver": str(approver).strip(), "plan_id": plan_id}

    try:
        result = adapter.restore(target)
        result["action"] = "restore_internet"
    except (NftablesError, CommandError) as exc:
        rollback = _attempt_rollback(adapter, previous, target)
        result = {
            "status": "failed",
            "action": "restore_internet",
            "error": exc.to_dict(),
            "rollback": rollback,
        }

    verification = _attempt_verification(adapter, target)
    result["verification"] = verification
    result["snapshot_id"] = snapshot.id
    result["consent"] = consent
    result["device"] = target.to_dict()
    if policy_id is not None:
        result["policy_id"] = policy_id

    success = (
        result["status"] in ("restored", "not_applied") and not verification["applied"]
    )
    if not success:
        if "rollback" not in result:
            result["rollback"] = _attempt_rollback(adapter, previous, target)
            verification = _attempt_verification(adapter, target)
            result["verification"] = verification
        result["status"] = "failed"

    record_status = "reverted" if success else "failed"
    record = _upsert_control(db, target, record_status, result, snapshot, verification)
    if success:
        record.nft_rule_handles_json = []
    db.commit()
    return result


def verify_internet_block(
    db: Session,
    device_id: int,
    *,
    config: NetworkEnforcementConfig | None = None,
    now=None,
    adapter: NftablesAdapter | None = None,
    authorized_networks=None,
    required_source_prefix=None,
):
    """Read-only verification of a device's Netra-owned blocking state."""
    config = config or NetworkEnforcementConfig.from_env()
    target = resolve_device_target(
        db,
        device_id,
        config=config,
        now=now,
        authorized_networks=authorized_networks,
        required_source_prefix=required_source_prefix,
    )
    adapter = adapter or _adapter_for_config(config)
    verification = adapter.verify(target)
    verification["device"] = target.to_dict()
    return verification


def rollback_internet_control(
    db: Session,
    device_id: int,
    *,
    config: NetworkEnforcementConfig | None = None,
    now=None,
    adapter: NftablesAdapter | None = None,
    snapshot_id: int | None = None,
):
    """Roll back a device to a recorded Netra-owned snapshot."""
    config = config or NetworkEnforcementConfig.from_env()
    _require_mutation_permitted(config)
    target = resolve_device_target(db, device_id, config=config, now=now)
    record = get_control_state(db, device_id, MODE_INTERNET_ACCESS)
    if snapshot_id is None:
        if record is None or record.snapshot_id is None:
            raise PlanError(
                "No snapshot is recorded for this device", code="snapshot_not_found"
            )
        snapshot_id = record.snapshot_id
    snapshot = db.get(ConfigSnapshot, snapshot_id)
    previous = _snapshot_state(snapshot)

    adapter = adapter or _adapter_for_config(config)
    result = adapter.rollback(previous, target)
    verification = adapter.verify(target)
    result["verification"] = verification
    if record is not None:
        record.status = "rolled_back"
        record.nft_rule_handles_json = verification.get("handles") or []
        record.details_json = {
            "verification": verification,
            "rollback": result,
        }
        db.add(record)
    db.commit()
    return result


def build_dry_run_plan(
    db: Session,
    request: NetworkControlRequest,
    *,
    config: NetworkEnforcementConfig | None = None,
    now=None,
    authorized_networks=None,
    required_source_prefix=None,
):
    """Validate identity and persist a no-change plan.

    Returns ``(plan_record, plan, impact)``. No nftables, tc, interface, router,
    or host firewall state is touched.
    """
    config = config or NetworkEnforcementConfig.from_env()
    action, upload, download = _validate_request(request)
    target = resolve_device_target(
        db,
        request.device_id,
        config=config,
        now=now,
        authorized_networks=authorized_networks,
        required_source_prefix=required_source_prefix,
    )

    command_plans, warnings, state = _commands_for_action(
        db, action, upload, download, target, config
    )
    blockers = _apply_blockers(config, action)

    plan = {
        "mode": "dry-run",
        "generated_at": (now or datetime.utcnow()).isoformat(),
        "action": action,
        "device": target.to_dict(),
        "config": config.to_dict(),
        "commands": [item.to_dict() for item in command_plans],
        "target_state": state,
        "warnings": warnings,
        "apply_allowed": not blockers,
        "apply_blockers": blockers,
        "safety": {
            "shell_execution": False,
            "command_timeout_seconds": config.command_timeout_seconds,
            "modifies_host_firewall": False,
            "flushes_nftables_tables": False,
            "replaces_existing_qdiscs": False,
            "uses_sudo": False,
        },
    }
    impact = {
        "affected_devices": [target.device_id],
        "scope": "single validated device",
        "network_change": False,
        "command_count": len(command_plans),
        "note": "Projection only; no firewall, qdisc, or interface was modified",
    }

    plan_record = DryRunPlan(plan_json=plan, impact_json=impact)
    db.add(plan_record)
    db.flush()
    _sync_planned_controls(db, target, action, state, plan_record.id)
    db.commit()
    db.refresh(plan_record)
    return plan_record, plan, impact
