# Installation

Backend:
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8084

Frontend:
cd frontend
npm install
npm run dev

Health: GET http://127.0.0.1:8084/api/health
CORS: backend allows http://localhost:5173, http://127.0.0.1:5173,
and http://[::1]:5173.

## Optional AdGuard Home DHCP Inventory

Netra can read the built-in DHCP lease list from a configured AdGuard Home
instance. Set these variables in the backend process environment; do not put
credentials in frontend configuration or source control:

```text
NETRA_ADGUARD_API_URL=http(s)://<gateway-ip>:<web-port>
NETRA_ADGUARD_USERNAME=<AdGuard Home username>
NETRA_ADGUARD_PASSWORD=<secret>
```

The URL hostname must match the router IP entered on the LAN Discovery page.
Router checks and LAN scans are limited to the active private subnet. To
authorize additional private networks, set a comma-separated backend allowlist:

```text
NETRA_AUTHORIZED_CIDRS=192.168.88.0/24,10.24.0.0/16
```

LAN scans remain capped at `/16` and must fit inside the active or explicitly
authorized network. Without Linux route detection, configure the allowlist for
the network you intend to use.

Netra issues a read-only request to AdGuard Home's DHCP status endpoint. If
the router or its DHCP server is unsupported/unconfigured, use LAN discovery;
no router settings are changed. AdGuard Home may not provide a read-only API
role, so the configured account can have broader privileges than Netra uses.
See
[Router Compatibility](ROUTER_COMPATIBILITY.md) for field and support limits.

## Real DNS monitoring (AdGuard Home / Pi-hole)

The same `NETRA_ADGUARD_*` variables enable DNS query monitoring. Start the
existing local lab (no duplicate instance) with:

```bash
docker compose -f docker-compose.adguard.yml up -d
```

Configure the backend process with:

```text
NETRA_ADGUARD_API_URL=http://127.0.0.1:3001
NETRA_ADGUARD_USERNAME=<AdGuard Home username>
NETRA_ADGUARD_PASSWORD=<secret>
NETRA_ADGUARD_TIMEOUT=5
NETRA_ADGUARD_CONNECT_TIMEOUT=3
NETRA_ADGUARD_MAX_EVENTS=500
NETRA_ADGUARD_PAGE_SIZE=100
NETRA_DNS_BACKEND=adguard
```

For Pi-hole v6 instead, set `NETRA_PIHOLE_URL` and `NETRA_PIHOLE_TOKEN` and
`NETRA_DNS_BACKEND=pihole`. Provider switching is env-driven; no settings API
stores credentials.

Enforcement is **off by default**. To permit consent-gated rule changes in the
local lab only, additionally set:

```text
NETRA_DNS_ENFORCEMENT_ENABLED=true
```

Never set this for a personal router unless you intend to change its DNS
filtering. Read-only monitoring, sync, analytics, audit, and dry-run all work
without it. See [AdGuard Home integration](ADGUARD_HOME_INTEGRATION.md).

## Optional hotspot client controls

The Connected Devices page discovers an existing Linux/NetworkManager Wi-Fi
hotspot and can prepare consent-gated per-device Internet-access changes.
Actual nftables changes are off by default and require an explicit opt-in,
`nft`, and appropriate privileges for the backend process. No router or
hotspot configuration is changed. Read the safety requirements and known
limitations in [Network enforcement](NETWORK_ENFORCEMENT.md) before enabling
the feature.

CORS: the backend allows `http://localhost:5173`, `http://127.0.0.1:5173`, and
`http://[::1]:5173`.
```