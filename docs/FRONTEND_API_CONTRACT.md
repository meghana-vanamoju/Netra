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
| `GET /api/audits` | Newest-first array of `{ "id": number, "scope": string, "created_at": string }`. Only saved reports are listed. |
| `POST /api/audits/run?scope=network` | Runs and saves a network audit; returns `{ "audit_id": number, "findings": number, "summary": { "devices": number, "findings": number } }`. |
| `POST /api/audits/run?scope=device&device_id={id}` | Runs and saves an audit for one inventory device; returns the same shape. |
| `GET /api/audits/{audit_id}` | `{ "id": number, "scope": string, "summary": { "devices": number, "findings": number }, "findings_count": number }`. |
| `GET /api/audits/{audit_id}/findings` | Array of `{ "id": string, "device_id": number \| null, "title": string, "description": string, "severity": string, "detection_rule": string, "evidence": string[], "timestamp": string, "recommended_next_step": string }`. |
| `GET /api/devices?limit=200` | Used to select a device audit target and associate device IDs in findings with inventory identity. |
| `GET /api/backend/capabilities` | `{ "configured_backend": string \| null, "available": boolean, "status": string }` |

Device records include `id`, `ip_address`, nullable `mac_address`, `hostname`,
`vendor`, and `discovery_source`, `first_seen`, `last_seen`, and nullable
`metadata`.

The dashboard overview reads these endpoints but does not start an audit,
modify a policy, or apply network configuration. A configured DNS backend indicates
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

## DNS analytics UI

| Method and path | Response and behavior |
|---|---|
| `GET /api/dns/analytics/summary` | `{ "total": number, "unique_domains": number, "by_category": { [category: string]: number } }`. |
| `GET /api/dns/analytics/domains?limit=20` | Array of `{ "domain": string, "count": number, "category": string }`, ordered by query count descending. |
| `GET /api/dns/analytics/devices` | Array of `{ "device_id": number \| null, "count": number }`; a null ID represents events not linked to an inventory device. |
| `GET /api/dns/events?limit=50&offset=0` | Newest-first array of `{ "id": number, "domain": string, "category": string \| null, "device_id": number \| null, "timestamp": string }`. Supports offset pagination and an optional `device_id` filter. |
| `GET /api/devices?limit=200` | Used to associate DNS device IDs with known inventory identity where available. |

DNS summary, domain, and device endpoints are aggregates; `/api/dns/events`
returns individual stored records. The explorer searches and filters only the
currently fetched event page, because the API does not expose text or category
filters. It requests pages of 50 and offers a next page when the backend returns
a full page; the event-list response has no total count. The domain list asks
for the top 20 and filters those returned rows locally.

The backend labels domains not matched by its configured rules as `Unknown`.
This is an absence of a category match, not a maliciousness verdict. The page
does not collect DNS traffic, trigger DNS queries, or change network settings.

## Privacy audit UI

The audit page reads the saved report list, report summary, findings, and device
inventory. It offers only the two scopes implemented by `POST /api/audits/run`:
`network` and `device` (with a required device ID for the latter). An audit is
never run on page load; the user must submit the form. The backend evaluates
inventory metadata and stored DNS events, then saves a report. It does not
perform a LAN scan or apply a policy.

The audit history endpoint lists saved reports only. It has no failed-run
records, status field, or device target in its report-list/detail responses.
Consequently, a listed report is a saved completion, while a failed or
interrupted request cannot be represented as a historical failed audit. A
successful run response confirms the report ID, finding count, and summary;
the UI labels completion only after that response. Finding severity and
evidence are displayed as returned and are not converted into a compromise
verdict or risk score.

## Policy planning UI

| Method and path | Response and behavior |
|---|---|
| `GET /api/audits` | Saved completed reports used as policy-plan inputs. |
| `GET /api/audits/{audit_id}/findings` | Finding list used to explain the backend's current generation rule. |
| `POST /api/policies/plan?audit_id={id}` | Generates and persists policies for matching findings; returns `{ "policies": number[] }` containing the created policy IDs. |
| `GET /api/policies` | Array of `{ "id": number, "name": string, "risk": string, "status": string }`. |
| `GET /api/policies/{policy_id}` | `{ "id": number, "name": string, "action": string, "risk": string, "reversible": boolean }`. |
| `POST /api/policies/dry-run` | JSON request body is an array of policy IDs. Returns `{ "plan_id": number, "plan": { "policies": number[], "affected_queries": number, "unique_domains": number }, "impact": { "projected_blocked_queries": number, "note": string } }` and persists a dry-run plan. |
| `GET /api/policies/dry-run/{plan_id}` | `{ "id": number, "plan": object }` for a saved dry-run plan. |
| `GET /api/policies/dry-run/{plan_id}/impact` | Saved impact object, including `projected_blocked_queries` and `note`. |

Policy planning matches audit finding titles containing “tracking” or
“telemetry”. The plan response only returns policy IDs; policy summaries do not
include descriptions, targets, audit linkage, or per-policy rationale. Policy
details expose action, risk, and reversibility but still omit the target.
Generated policy IDs are linked to an audit in the UI only for the current
planning response; that relationship is not persisted or exposed by the API.
The planner creates a new policy for each matching finding and exposes no
deduplication or idempotency guarantee; repeated requests may create additional
records.

Dry-run projections count stored DNS events in Advertising,
Tracking/Analytics, and Telemetry categories except exact domains
`google.com`, `microsoft.com`, and `apple.com`. The response has aggregate
counts, not per-policy attribution or an affected-domain list. Both planning
and dry-run are explicit write operations: planning saves proposed policies,
and dry-run saves a plan record. The planning UI does not approve, apply, or
enforce policies. A projected blocked-query count is not evidence that traffic
was blocked or that protection is active.

## Errors and pagination

API errors use JSON shaped as `{ "detail": "..." }`. Device inventory accepts
`limit` and `offset`; `limit` is capped at 200. The dashboard requests the
first 200 records and labels a full page as a lower bound rather than claiming
it is the total inventory.
