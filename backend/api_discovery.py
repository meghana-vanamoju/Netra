import logging
import subprocess
from datetime import datetime, timezone
from time import monotonic
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from db.session import get_db
from discovery.service import (
    DiscoveryUnavailableError,
    discover_subnet,
    get_local_network_info,
    validate_subnet,
)
from discovery.unified import merge_devices, replace_discovery_snapshot

router = APIRouter(prefix="/api/discovery", tags=["discovery"])
_results = []
_results_by_subnet = {}
_last_scan_by_subnet = {}
_router_results = []
logger = logging.getLogger(__name__)


def _scan_metrics(metrics: dict, duration: float) -> dict:
    return {
        "duration_seconds": round(duration, 3),
        "probes_attempted": metrics.get("probes_attempted", 0),
        "hosts_responding": metrics.get("hosts_responding", 0),
        "timeout_count": metrics.get("timeout_count", 0),
        "probe_errors": metrics.get("probe_errors", 0),
        "partial_results": metrics.get("partial_results", False),
    }


def canonicalize_subnet(value: str) -> str:
    """Return the CIDR string a query parameter was meant to carry.

    Query values arrive percent-encoded from browsers (``/`` becomes ``%2F``).
    Some clients and browser URL handling add another encoding layer, so the
    route can receive a literal ``%2F`` instead of a slash. Decoding a bounded
    number of times restores the canonical value before validation; no
    authorization rule is relaxed here.
    """
    canonical = value.strip()
    for _ in range(3):
        decoded = unquote(canonical)
        if decoded == canonical:
            break
        canonical = decoded
    return canonical.strip()


def record_router_results(devices):
    global _router_results
    _router_results = devices


@router.get("/network")
def network():
    return get_local_network_info()


@router.post("/run")
def run_discovery(subnet: str = "192.168.1.0/24", db: Session = Depends(get_db)):
    global _results
    subnet = canonicalize_subnet(subnet)
    try:
        validate_subnet(subnet)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_subnet", "message": str(e)},
        )

    started = monotonic()
    metrics = {}
    logger.info("LAN discovery started subnet=%s", subnet)
    try:
        discovered = discover_subnet(subnet, metrics=metrics)
    except DiscoveryUnavailableError:
        duration = monotonic() - started
        logger.warning(
            "LAN discovery failed subnet=%s duration_seconds=%.3f probes_attempted=%d hosts_responding=%d partial_results=%s code=probe_unavailable",
            subnet,
            duration,
            metrics.get("probes_attempted", 0),
            metrics.get("hosts_responding", 0),
            metrics.get("partial_results", False),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "probe_unavailable",
                "message": "LAN probes could not be started on this host.",
                **_scan_metrics(metrics, duration),
            },
        )
    except (OSError, subprocess.SubprocessError):
        duration = monotonic() - started
        logger.warning(
            "LAN discovery failed subnet=%s duration_seconds=%.3f probes_attempted=%d hosts_responding=%d partial_results=%s code=probe_failed",
            subnet,
            duration,
            metrics.get("probes_attempted", 0),
            metrics.get("hosts_responding", 0),
            metrics.get("partial_results", False),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "probe_failed",
                "message": "The LAN scan could not be completed by this host.",
                **_scan_metrics(metrics, duration),
            },
        )

    try:
        replace_discovery_snapshot(
            db,
            subnet,
            discovered,
            scan_partial=metrics.get("partial_results", False),
            probed_addresses=metrics.get("probed_addresses"),
            coverage_complete=metrics.get("coverage_complete"),
        )
    except SQLAlchemyError:
        db.rollback()
        duration = monotonic() - started
        logger.warning(
            "LAN discovery failed subnet=%s duration_seconds=%.3f probes_attempted=%d hosts_responding=%d partial_results=%s code=inventory_persistence_failed",
            subnet,
            duration,
            metrics.get("probes_attempted", 0),
            metrics.get("hosts_responding", 0),
            metrics.get("partial_results", False),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "inventory_persistence_failed",
                "message": "Discovery completed, but inventory could not be saved.",
                **_scan_metrics(metrics, duration),
            },
        )

    _results = discovered
    _results_by_subnet[subnet] = discovered
    duration = round(monotonic() - started, 3)
    response = {
        "discovered": len(discovered),
        "subnet": subnet,
        "scan_status": "partial"
        if metrics.get("partial_results", False)
        or not metrics.get("coverage_complete", True)
        else "complete",
        "coverage": {
            "hosts_in_subnet": metrics.get("hosts_in_subnet", 0),
            "hosts_probed": metrics.get("hosts_probed", 0),
            "coverage_complete": metrics.get("coverage_complete", True),
            "unprobed_hosts": max(
                0,
                metrics.get("hosts_in_subnet", 0)
                - metrics.get("hosts_probed", 0),
            ),
        },
    }
    response.update(_scan_metrics(metrics, duration))
    response["last_scan_at"] = datetime.now(timezone.utc).isoformat()
    _last_scan_by_subnet[subnet] = response
    logger.info(
        "LAN discovery completed subnet=%s duration_seconds=%.3f discovered=%d probes_attempted=%d hosts_responding=%d timeout_count=%d partial_results=%s",
        subnet,
        duration,
        response["discovered"],
        response["probes_attempted"],
        response["hosts_responding"],
        response["timeout_count"],
        response["partial_results"],
    )
    return response


@router.get("/status")
def discovery_status(subnet: str | None = None):
    """Return the last completed LAN scan for a subnet, with coverage facts."""
    if subnet:
        canonical = canonicalize_subnet(subnet)
        result = _last_scan_by_subnet.get(canonical)
        if result is None:
            return {"scanned": False, "subnet": canonical}
        return {"scanned": True, **result}
    if not _last_scan_by_subnet:
        return {"scanned": False, "subnet": None}
    latest = max(
        _last_scan_by_subnet.values(),
        key=lambda item: item.get("last_scan_at") or "",
    )
    return {"scanned": True, **latest}


@router.get("/results")
def results(subnet: str | None = None):
    """Return LAN observations only; router inventory has a separate endpoint."""
    if subnet:
        current = _results_by_subnet.get(subnet, [])
    else:
        current = _results
    return merge_devices(current, [])
