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
verification, and recovery APIs. These are not invoked by the dashboard
foundation.

## Errors and pagination

API errors use JSON shaped as `{ "detail": "..." }`. Device inventory accepts
`limit` and `offset`; `limit` is capped at 200. The dashboard requests the
first 200 records and labels a full page as a lower bound rather than claiming
it is the total inventory.
