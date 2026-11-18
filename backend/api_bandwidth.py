"""Bounded, permission-safe local interface bandwidth sampler.

This reads kernel interface counters from ``/proc/net/dev``. It measures traffic
on the Netra host only. It is not a router-wide or per-client monitor, and it
does not use packet capture or require elevated privileges.
"""

import os
import re
import threading
import time
from collections import deque
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_db

router = APIRouter(prefix="/api/bandwidth", tags=["bandwidth"])

PROC_NET_DEV = "/proc/net/dev"
DEFAULT_SAMPLE_INTERVAL_MS = 1000
MIN_SAMPLE_INTERVAL_MS = 200
MAX_SAMPLE_INTERVAL_MS = 5000
MAX_HISTORY = 240
INTERFACE_PATTERN = re.compile(r"^[A-Za-z0-9_.:@-]{1,32}$")

_lock = threading.Lock()
_history: dict[str, deque] = {}


def _counters() -> dict[str, dict[str, int]]:
    try:
        with open(PROC_NET_DEV, encoding="utf-8") as handle:
            lines = handle.readlines()[2:]
    except OSError:
        raise HTTPException(
            503,
            "Interface counters are unavailable on this host; Linux /proc/net/dev is required.",
        ) from None

    result = {}
    for line in lines:
        if ":" not in line:
            continue
        name, values = line.split(":", 1)
        fields = values.split()
        if len(fields) < 16:
            continue
        name = name.strip()
        if not INTERFACE_PATTERN.match(name):
            continue
        try:
            result[name] = {
                "rx_bytes": int(fields[0]),
                "rx_packets": int(fields[1]),
                "tx_bytes": int(fields[8]),
                "tx_packets": int(fields[9]),
            }
        except ValueError:
            continue
    return result


def _default_interface(counters: dict[str, dict[str, int]]) -> Optional[str]:
    from discovery.service import get_local_network_info

    candidate = get_local_network_info().get("interface")
    if candidate in counters:
        return candidate
    for name in counters:
        if name != "lo":
            return name
    return "lo" if "lo" in counters else None


def _validate_interface(interface: Optional[str], counters: dict[str, dict[str, int]]) -> str:
    if interface is None:
        selected = _default_interface(counters)
        if not selected:
            raise HTTPException(503, "No network interface counters are available")
        return selected
    name = interface.strip()
    if not INTERFACE_PATTERN.match(name):
        raise HTTPException(400, "Invalid interface name")
    if name not in counters:
        raise HTTPException(404, "Interface was not found in the host counter table")
    return name


def _sample_from_counters(before, after, interval_seconds: float) -> dict:
    rx_delta = max(0, after["rx_bytes"] - before["rx_bytes"])
    tx_delta = max(0, after["tx_bytes"] - before["tx_bytes"])
    return {
        "interface": None,
        "sampled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "interval_seconds": round(interval_seconds, 3),
        "rx_bytes_per_second": round(rx_delta / interval_seconds, 2),
        "tx_bytes_per_second": round(tx_delta / interval_seconds, 2),
        "rx_bytes_total": after["rx_bytes"],
        "tx_bytes_total": after["tx_bytes"],
        "rx_packets_total": after["rx_packets"],
        "tx_packets_total": after["tx_packets"],
        "rx_bytes_delta": rx_delta,
        "tx_bytes_delta": tx_delta,
        "scope": "netra-host-interface",
    }


@router.get("/interfaces")
def interfaces():
    counters = _counters()
    active = _default_interface(counters)
    return [
        {
            "name": name,
            "active": name == active,
            "rx_bytes_total": values["rx_bytes"],
            "tx_bytes_total": values["tx_bytes"],
        }
        for name, values in sorted(counters.items())
    ]


@router.get("/status")
def status(interface: Optional[str] = None, db: Session = Depends(get_db)):
    del db  # Kept for dependency symmetry with other read endpoints.
    counters = _counters()
    selected = _validate_interface(interface, counters)
    with _lock:
        history = list(_history.get(selected, []))
    latest = history[-1] if history else None
    return {
        "interface": selected,
        "active_interface": _default_interface(counters),
        "monitoring": latest is not None,
        "sampling_interval_ms": DEFAULT_SAMPLE_INTERVAL_MS,
        "retention_samples": MAX_HISTORY,
        "sample_count": len(history),
        "latest": latest,
        "cumulative": {
            "rx_bytes": counters[selected]["rx_bytes"],
            "tx_bytes": counters[selected]["tx_bytes"],
            "rx_packets": counters[selected]["rx_packets"],
            "tx_packets": counters[selected]["tx_packets"],
        },
        "scope": "netra-host-interface",
        "message": (
            "Traffic measured on the Netra host interface. This does not measure every router client."
        ),
    }


@router.post("/sample")
def sample(interface: Optional[str] = None, interval_ms: int = DEFAULT_SAMPLE_INTERVAL_MS):
    interval = max(
        MIN_SAMPLE_INTERVAL_MS, min(MAX_SAMPLE_INTERVAL_MS, int(interval_ms))
    )
    before_all = _counters()
    selected = _validate_interface(interface, before_all)
    before = before_all[selected]
    time.sleep(interval / 1000)
    after_all = _counters()
    if selected not in after_all:
        raise HTTPException(503, "Interface disappeared while sampling")
    result = _sample_from_counters(before, after_all[selected], interval / 1000)
    result["interface"] = selected
    with _lock:
        series = _history.setdefault(selected, deque(maxlen=MAX_HISTORY))
        series.append(result)
    return result


@router.get("/history")
def history(interface: Optional[str] = None, limit: int = 60):
    counters = _counters()
    selected = _validate_interface(interface, counters)
    size = max(1, min(MAX_HISTORY, int(limit)))
    with _lock:
        rows = list(_history.get(selected, []))[-size:]
    return {
        "interface": selected,
        "retention_samples": MAX_HISTORY,
        "returned": len(rows),
        "samples": rows,
    }
