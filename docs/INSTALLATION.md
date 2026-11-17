# Installation

Backend:
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

Frontend:
cd frontend
npm install
npm run dev

Health: GET http://127.0.0.1:8000/api/health
CORS: backend allows localhost:5173 and 127.0.0.1:5173.

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
```