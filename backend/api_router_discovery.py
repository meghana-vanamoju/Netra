import os
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api_discovery import record_router_results
from db.session import get_db
from dns.providers.adguard import AdGuardHomeAdapter
from discovery.router.adapter import validate_router_ip, RouterAdapter
from discovery.unified import upsert_inventory

router = APIRouter(prefix="/api/router", tags=["router"])


@router.post("/test")
def test_router(ip: str):
    if not validate_router_ip(ip):
        raise HTTPException(400, "Invalid IP")
    ad = RouterAdapter(ip)
    return {
        "ip": ip,
        "reachable": ad.reachable(),
        "network_reachable": ad.network_reachable(),
        "management_interface_available": ad.management_interface_available(),
    }


@router.get("/capabilities")
def caps(ip: str):
    if not validate_router_ip(ip):
        raise HTTPException(400, "Invalid IP")
    result = RouterAdapter(ip).capabilities()
    adapter = _configured_adguard(ip)
    result["adguard_home_configured"] = adapter is not None
    if adapter:
        result["management_protocols"] = ["AdGuard Home HTTP API"]
        result["connected_devices"] = "configured"
        result["dhcp_leases"] = "configured"
    return result


@router.get("/adguard/status")
def adguard_status(ip: str):
    if not validate_router_ip(ip):
        raise HTTPException(400, "Router IP must be a private IPv4 address")
    adapter = _configured_adguard(ip)
    if not adapter:
        return {
            "configured": False,
            "provider_state": "not_configured",
            "router_ip": ip,
            "filtering_enabled": None,
            "filter_count": None,
            "dhcp_inventory": "unsupported",
            "network_wide_enforcement": "not_verified",
            "guidance": [
                "Configure NETRA_ADGUARD_API_URL and credentials on the backend.",
                "Set the router DHCP DNS servers to the AdGuard Home network address.",
                "Verify clients send DNS queries by reviewing the provider query log.",
            ],
        }
    try:
        filtering = adapter.filtering_status()
        dhcp = adapter.dhcp_status()
        dhcp_available = isinstance(dhcp, dict)
    except httpx.TimeoutException:
        raise HTTPException(503, "AdGuard Home request timed out") from None
    except httpx.HTTPStatusError:
        raise HTTPException(
            503, "AdGuard Home credentials or API access failed"
        ) from None
    except (httpx.HTTPError, RuntimeError, ValueError):
        raise HTTPException(503, "AdGuard Home is unavailable") from None
    return {
        "configured": True,
        "provider_state": "healthy",
        "router_ip": ip,
        "filtering_enabled": filtering["enabled"],
        "filter_count": filtering["filter_count"],
        "user_rule_count": len(filtering["user_rules"]),
        "dhcp_inventory": "available" if dhcp_available else "unknown",
        "network_wide_enforcement": "not_verified",
        "guidance": [
            "Filtering is server-side; this does not prove router DHCP uses AdGuard Home.",
            "Configure the router DHCP DNS server with the AdGuard Home address using the router vendor UI.",
            "Do not assume VPN, HTTPS DNS, hardcoded DNS or encrypted resolvers are blocked.",
            "Verify a client query in AdGuard Home before claiming network-wide protection.",
        ],
    }


@router.post("/devices")
def router_devices(ip: str, db: Session = Depends(get_db)):
    if not validate_router_ip(ip):
        raise HTTPException(400, "Router IP must be a private IPv4 address")
    adapter = _configured_adguard(ip)
    if not adapter:
        record_router_results([])
        return {
            "router_ip": ip,
            "status": "unsupported",
            "authentication_required": "unknown",
            "devices": [],
        }
    try:
        devices = adapter.collect()
    except httpx.HTTPStatusError as error:
        record_router_results([])
        if error.response.status_code == 401:
            return {
                "router_ip": ip,
                "status": "authentication_required",
                "authentication_required": True,
                "devices": [],
            }
        return {
            "router_ip": ip,
            "status": "access_denied" if error.response.status_code == 403 else "error",
            "authentication_required": "unknown",
            "devices": [],
        }
    except httpx.TimeoutException:
        record_router_results([])
        return {
            "router_ip": ip,
            "status": "timeout",
            "authentication_required": "unknown",
            "devices": [],
        }
    except (httpx.HTTPError, ValueError, RuntimeError):
        record_router_results([])
        return {
            "router_ip": ip,
            "status": "error",
            "authentication_required": "unknown",
            "devices": [],
        }
    upsert_inventory(db, devices)
    record_router_results(devices)
    return {
        "router_ip": ip,
        "status": "available",
        "authentication_required": "configured" if adapter.username else False,
        "devices": devices,
    }


def _configured_adguard(ip: str):
    url = os.environ.get("NETRA_ADGUARD_API_URL", "").strip()
    if not url or urlsplit(url).hostname != ip:
        return None
    return AdGuardHomeAdapter(
        url=url,
        username=os.environ.get("NETRA_ADGUARD_USERNAME"),
        password=os.environ.get("NETRA_ADGUARD_PASSWORD"),
    )
