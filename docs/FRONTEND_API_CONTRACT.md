# Netra Frontend API Contract

The frontend uses `http://127.0.0.1:8084` by default. Configure another origin
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

## Settings and backend status UI

The read-only Settings & Backend page uses:

| Method and path | Response |
|---|---|
| `GET /api/health` | `{ "status": string, "service": string, "version": string }`; `status: "ok"` confirms the API health handler responded. |
| `GET /api/db/health` | `{ "status": string }`; currently performs a database `SELECT 1` health check. |
| `GET /api/backend/capabilities` | `{ "configured_backend": string \| null, "available": boolean, "status": string }`. The backend name comes from server-side `NETRA_DNS_BACKEND`; `available` means configured, not operational policy enforcement. |

There is no backend settings read/write API. `NETRA_DNS_BACKEND` must be
configured outside the dashboard, and the UI has no mutation controls.
Capability descriptions are based on implemented backend routes: discovery,
DNS analytics, and policy planning APIs exist; planning and dry-run persist
records. The policy adapter does not implement enforcement, verification
currently returns `not_verified`, snapshot rollback is not implemented, and
the recovery endpoint returns fixed status values without restoring state.
Service health and database health do not indicate active network protection.

## Other API families

The backend also exposes device discovery and classification, DNS events and
analytics, audits, policy planning and consent, snapshots, enforcement,
verification, and recovery APIs.

## Device inventory and discovery UI

| Method and path | Response and behavior |
|---|---|
| `GET /api/devices?limit=200&offset=0&live=true&subnet=` | Live snapshot records when `live=true`; historical records remain available without `live`. Stable MAC identity is preferred, IP is a fallback. |
| `GET /api/classifications` | Array of `{ "device_id": number, "category": string, "confidence": number, "reasons": string[], "vendor_identified": boolean }`. |
| `POST /api/devices/{device_id}/classify` | Recalculates and returns one device's classification; it does not persist the result. The UI only calls this after the user requests recalculation in device details. |
| `POST /api/discovery/run?subnet={cidr}` | `{ "discovered": number, "subnet": string, "duration_seconds": number, "probes_attempted": number, "hosts_responding": number, "timeout_count": number, "probe_errors": number, "partial_results": boolean }`. Requires a private IPv4 subnet within the active network or `NETRA_AUTHORIZED_CIDRS`, capped at `/16`; scan records are persisted to inventory. |
| `GET /api/discovery/network` | `{ "interface": string \| null, "ip_address": string \| null, "gateway": string \| null, "subnet": string \| null }`; reads the active default route and interface address when Linux `ip` is available. |
| `POST /api/router/test?ip={ipv4}` | `{ "ip": string, "reachable": boolean, "network_reachable": boolean, "management_interface_available": boolean }`; `reachable` means local neighbor evidence only, not management support. |
| `GET /api/router/capabilities?ip={ipv4}` | Reports implemented capabilities and whether an exact-IP AdGuard Home adapter is configured. Generic open ports do not imply router support. |
| `POST /api/router/devices?ip={ipv4}` | `{ "router_ip": string, "status": string, "authentication_required": boolean \| string, "devices": [...] }`; uses only explicitly configured AdGuard Home built-in DHCP leases. Successful records update the device inventory. |
| `GET /api/discovery/results` | Latest in-memory LAN results merged with the most recent router records. Each record includes `ip_address`, nullable `mac_address`/`hostname`, `discovery_source`, and merged `sources`. |

Discovery only runs after a user action. It uses no more than eight concurrent
single-packet ICMP probes, a 1.25-second per-host process deadline, and a
12-second overall scan deadline; no more than 64 hosts are attempted. Partial
results can be returned at the overall deadline. An ICMP no-reply is counted as
a timeout, not proof that a device is absent. The backend reports successful
ICMP responders and newly observed Linux neighbor entries; unchanged cached
entries are not treated as new discoveries. MAC addresses require a complete
neighbor-table entry. Reverse DNS is disabled by default, and missing hostnames
or vendor details remain unknown. Current results are process-local and may be
lost on backend restart; persistent device records remain available through
`/api/devices`. Client isolation, permissions, and host firewall behavior can
limit visibility. Configure `NETRA_AUTHORIZED_CIDRS` on the backend to allow
private networks other than the active interface subnet.

Invalid subnets return HTTP 400 with a structured `detail.code` and
`detail.message`. Probe or inventory failures return a sanitized HTTP 503
response with the same error fields and available scan telemetry.

The supported router adapter is restricted to AdGuard Home's documented
`GET /control/dhcp/status` API. It maps dynamic/static lease IP, MAC, hostname,
and expiry; vendor, online state, and last seen are unknown unless another
source provides evidence. Other router models are reported unsupported. See
[Router Integration Architecture](ROUTER_INTEGRATION_ARCHITECTURE.md) and
[Router Compatibility](ROUTER_COMPATIBILITY.md).

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

## Enforcement and recovery UI

The Enforcement readiness page uses read endpoints for evidence and an explicit
consent-gated apply/verify/rollback workflow for saved policies:

| Method and path | Response |
|---|---|
| `GET /api/enforcement/status` | `{ "available": boolean, "backend": string \| null, "enabled": boolean, "provider_state": string }`. `available` is provider presence; `enabled` reflects the explicit opt-in flag. |
| `GET /api/recovery/status` | `{ "recovery_ready": boolean, "interrupted_executions": number, "failed_executions": number }`, now derived from policy state rather than fixed values. |
| `GET /api/snapshots` | Array of `{ "id": number, "backend": string \| null, "created_at": string, "checksum": string \| null }`. |
| `GET /api/snapshots/{snapshot_id}` | `{ "id": number, "state": object \| null, "checksum": string \| null, "integrity_ok": boolean }`. `integrity_ok` reports a checksum comparison, not whether the state is currently applied. |
| `GET /api/policies` | Saved policy summaries used to select a policy for status inspection. |
| `GET /api/policies/{policy_id}/approval` | `{ "status": string, "approver": string \| null, "approved_at": string \| null, "plan_id": number \| null }`. The status is the saved policy status and is not an independent consent decision. |
| `GET /api/policies/{policy_id}/execution` | `{ "status": string, "details": object \| null }`; returns 404 if no execution record exists. |
| `GET /api/policies/{policy_id}/rollback-status` | `{ "policy_id": number, "status": string, "rollback_ready": boolean }`. This is a status flag only. |
| `GET /api/verification/policy/{policy_id}` | `{ "policy_id", "status": "verified" \| "not_verified", "provider", "evidence", "reason" }`; `verified` requires real provider query-log evidence. |

Consent-gated actions are available only after a policy is selected and the
confirmation checkbox is checked:
`POST /api/policies/{id}/approve?plan_id=&confirm=true`,
`POST /api/policies/{id}/apply`, and
`POST /api/snapshots/{id}/rollback?confirm=true`. They are only usable with a
configured provider and explicit opt-in. Verification status is read back after
apply and is never inferred from the apply response. Show loading, error, empty,
and success states; never label a configured backend as active protection.

## Completed page contracts

| Method and path | Frontend use |
|---|---|
| `GET /api/dashboard/summary?subnet=` | Live overview cards. Every value is backend-reported; unconfigured/unavailable states are explicit. |
| `GET /api/discovery/status` | Bounded scan coverage and last-scan timestamp. |
| `GET /api/bandwidth/interfaces`, `GET /api/bandwidth/status`, `POST /api/bandwidth/sample`, `GET /api/bandwidth/history` | Host-local sampler. The UI labels all rates as `netra-host-interface`, never router-wide. |
| `GET /api/enforcement/readiness` | Gateway, interface, permissions, supported/unsupported modes, warnings and snapshot count. |
| `GET /api/diagnostics/adguard` | Provider status, filtering, statistics, query-log evidence and independent router DHCP/DNS verification status. |
| `GET /api/dns/events?domain=` | DNS event search/filter. |
| `POST /api/dns/providers/filtering/refresh?confirm=true` | Explicit provider reload where supported. |
| `POST /api/dns/providers/filtering/rules` | `block`, `unblock`, `allow`, `remove` actions with `confirm: true`. |
| `POST /api/policies`, `PUT /api/policies/{id}`, `DELETE /api/policies/{id}?confirm=true` | Saved device policy CRUD with target, enabled state and supported DNS rules. |
| `POST /api/policies/preview?audit_id={id}` | Non-persistent policy drafts. |
| `POST /api/snapshots/from-provider` | Captures real provider user rules, explicitly not a database backup. |
| `GET /api/privacy/score`, `POST /api/policies/preview?audit_id={id}` | Evidence-backed score and dry-run policy drafts. |

## Errors and pagination

API errors use JSON shaped as `{ "detail": "..." }`. For provider failures the
detail is an object with `state` and `message`; `api.ts` surfaces the message.
Device inventory accepts `limit` and `offset`; `limit` is capped at 200. The
dashboard requests the first 200 records and labels a full page as a lower
bound rather than claiming it is the total inventory.

## Milestone 9.0 provider handoff for Copilot

No existing UI page was redesigned. The additive client surface is:

- `getDnsProviderStatus()` → `DnsProviderStatus`; render `state` with distinct
  loading/error/empty states. Only `healthy` may be shown as connected.
- `getDnsProviderStatistics()` → provider counters; show null as unknown.
- `getDnsProviderFiltering()` → `enabled`, `user_rules`, `filter_count`.
- `syncDnsEvents()` → `DnsSyncResult`; use a busy state, then refresh summary,
  events, and domains. A 503 means the provider is unavailable, not an empty
  log.
- `DnsSummary` now includes `blocked`, `allowed`, `blocking_percentage`,
  `top_blocked_domains`, `by_client`, `by_source`, `timeline`, and
  `category_evidence`. Treat null percentages as unknown.
- `DnsEvent` now includes `blocked`, `query_type`, `client`, `client_name`,
  `reason`, `rules`, `upstream`, `source`, and `confidence`. Label sources:
  `adguard-home`, `pihole`, `manual`, `synthetic-demo`.

Suggested components: a provider status badge on the DNS analytics page, a
"Sync provider" button, blocked/allowed cards, a category evidence panel, and
an optional consent-gated policy drawer that links to existing approval,
execution, verification, and rollback endpoints. These are UI tasks for
Copilot; backend API and TypeScript types are ready.
