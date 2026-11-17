from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db
from discovery.service import discover_subnet, get_local_network_info, validate_subnet
from discovery.unified import merge_devices, upsert_inventory

router = APIRouter(prefix="/api/discovery", tags=["discovery"])
_results = []
_router_results = []


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
        raise HTTPException(status_code=400, detail=str(e))
    discovered = discover_subnet(subnet)
    _results = discovered
    upsert_inventory(db, discovered)
    return {"discovered": len(discovered), "subnet": subnet}


@router.get("/results")
def results():
    return merge_devices(_results, _router_results)
