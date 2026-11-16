# Netra Frontend API Contract

The frontend uses `http://localhost:8000` by default. Configure another origin
with `VITE_API_BASE_URL`. The backend must allow the frontend origin through
CORS.

## Dashboard read endpoints

| Method and path | Response |
|---|---|
| `GET /api/health` | `{ "status": "ok", "service": "netra-backend", "version": "0.1.0" }` |
| `GET /api/db/health` | `{ "status": "ok" }` |
| `GET /api/devices?limit=200` | Array of device records. The API accepts up to 200 records per request. |
| `GET /api/dns/analytics/summary` | `{ "total": number, "unique_domains": number, "by_category": { [category: string]: number } }` |
| `GET /api/audits` | Array of `{ "id": number, "scope": string, "created_at": string }` |
| `GET /api/audits/{audit_id}` | `{ "id": number, "scope": string, "summary": object, "findings_count": number }` |
| `GET /api/audits/{audit_id}/findings` | Array of saved audit finding records. |
| `GET /api/backend/capabilities` | `{ "configured_backend": string \| null, "available": boolean, "status": string }` |

Device records include `id`, `ip_address`, nullable `mac_address`, `hostname`,
`vendor`, and `discovery_source`, `first_seen`, `last_seen`, and nullable
`metadata`.

The dashboard reads only these endpoints. It does not start an audit, modify a
policy, or apply network configuration. A configured DNS backend indicates
configuration only; it does not indicate active enforcement.

## Other API families

The backend also exposes device discovery and classification, DNS events and
analytics, audits, policy planning and consent, snapshots, enforcement,
verification, and recovery APIs.

## Device inventory and discovery UI

| Method and path | Response and behavior |
|---|---|
| `GET /api/devices?limit=200&offset=0` | Array of device records; the UI searches and paginates the returned first 200 locally. |
| `GET /api/classifications` | Array of `{ "device_id": number, "category": string, "confidence": number, "reasons": string[], "vendor_identified": boolean }`. |
| `POST /api/devices/{device_id}/classify` | Recalculates and returns one device's classification; it does not persist the result. The UI only calls this after the user requests recalculation in device details. |
| `POST /api/discovery/run?subnet={cidr}` | `{ "discovered": number, "subnet": string }`. Validates that the subnet is private, then synchronously scans and registers discoveries in the inventory. |
| `GET /api/discovery/results` | Most recent in-memory discovery results: an array of `{ "ip_address": string, "mac_address": string \| null, "hostname": string \| null, "discovery_source": string }`. |

Discovery only runs after the user submits a private subnet in the LAN
discovery screen. The backend probes up to 64 host addresses and reads its
local ARP table; it provides no progress stream, scan history, or permission
diagnostic. Results are process-local and may be lost on backend restart. A
zero result is not proof that the subnet has no devices. A discovery success
response confirms the endpoint completed and returned a count, not complete
network coverage. The UI limits CIDR ranges to private IPv4 networks no larger
than `/16`, avoiding excessively large ranges for this synchronous endpoint.

Classification is read from the existing endpoint and is not persisted or
changed by this UI. `Unknown` remains an explicit category when the backend
does not have enough evidence.

## Errors and pagination

API errors use JSON shaped as `{ "detail": "..." }`. Device inventory accepts
`limit` and `offset`; `limit` is capped at 200. The dashboard requests the
first 200 records and labels a full page as a lower bound rather than claiming
it is the total inventory.
