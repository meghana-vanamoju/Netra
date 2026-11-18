# API Reference

All paths are relative to `http://127.0.0.1:8084` unless `VITE_API_BASE_URL`
says otherwise. No built-in authentication is provided; protect the backend
with your own reverse proxy if it is exposed beyond loopback.

## Core

- `GET /api/health` — service health.
- `GET /api/db/health` — `SELECT 1` database check.
- `GET /api/devices`, `POST /api/devices`, `GET /api/devices/{id}`.
- `GET /api/discovery/results?subnet=`, `POST /api/discovery/run`, router discovery routes.
  - Discovery results are the latest selected-subnet process snapshot, not all inventory history.
  - `GET /api/devices?live=true&subnet=` returns only the latest snapshot for that subnet.
  - Historical devices remain available from `GET /api/devices` and are never labeled offline by discovery timeouts.
- `GET /api/classifications/...`.

## LAN discovery

`POST /api/discovery/run?subnet={cidr}` requires a private IPv4 subnet within
the active interface subnet or `NETRA_AUTHORIZED_CIDRS`. The backend performs
at most 64 single-packet ICMP probes with at most eight concurrent workers. A
probe process is limited to 1.25 seconds; the complete probe and optional
reverse-DNS work share a 12-second overall deadline. Reverse DNS is disabled
for API scans by default. A deadline or individual host timeout can produce a
successful partial response rather than discarding observations already made.

Successful responses retain the original fields and add scan telemetry:

```json
{
  "discovered": 15,
  "subnet": "192.168.88.0/24",
  "duration_seconds": 7.256,
  "probes_attempted": 64,
  "hosts_responding": 15,
  "timeout_count": 49,
  "probe_errors": 0,
  "partial_results": true
}
```

`hosts_responding` counts successful ICMP replies. `timeout_count` includes
ICMP no-reply outcomes and subprocess deadline expirations. `discovered` counts
records supported by successful replies or newly observed neighbor entries;
unchanged cached entries are not refreshed as new observations. MAC values are
included only from complete Linux neighbor entries, and reverse-DNS hostnames
are omitted by default.

Invalid or unauthorized subnets return HTTP 400 with
`{"detail":{"code":"invalid_subnet","message":"..."}}`. Probe or
inventory failures return sanitized HTTP 503 details with a `code`, `message`,
and the available scan telemetry. No stack trace or raw subprocess output is
returned to the frontend.

## DNS provider and query data

- `GET /api/dns/events` supports `device_id`, `client_ip`, `linked=true|false`,
  `blocked=true|false`, `source`, `limit`, and `offset`. Each linked event includes
  the device name, IP, and MAC; unlinked events remain explicitly `device_id:null`.
- `GET /api/dns/analytics/devices` returns total, blocked, and allowed events per
  linked/unlinked device group.
- `GET /api/dns/analytics/domains?device_id=` supports device-scoped domain totals.
- `POST /api/dns/events/sync` fetches real provider query logs and persists them
  idempotently. Events associate by exact verified client IP or configured
  AdGuard/host name mapping; no domain or identity is inferred from LAN discovery alone.
- `GET /api/dns/providers/filtering` reports provider filtering status.
- `POST /api/dns/providers/filtering/rules` blocks or unblocks a domain. It requires
  `confirm:true`, explicit DNS enforcement opt-in, and an AdGuard-compatible provider.
  This changes only provider user rules, not router DHCP/DNS.

## Router and AdGuard Home status

- `GET /api/router/adguard/status?ip=` reports provider configuration, filtering
  status, DHCP inventory evidence, and network-wide verification guidance.
  Network-wide enforcement remains `not_verified` until router DHCP/DNS and client
  query evidence confirm it. It does not claim HTTPS, encrypted-DNS, VPN or
  hardcoded-DNS bypass protection.


- `GET /api/dns/providers/status`
  - Sanitized state: `healthy`, `not_configured`, `unreachable`, `unauthorized`,
    `timeout`, `unsupported_api`, `malformed_response`, or `provider_unavailable`.
  - Includes real provider version, authentication state, and capability probe
    results for query log, statistics, and filtering. Never contains secrets.
- `GET /api/dns/providers/statistics` — provider statistics (503 on failure).
- `GET /api/dns/providers/filtering` — filtering state and user rules (503 on failure).
- `POST /api/dns/events/sync` — fetch real provider queries, store new ones, and
  return `{provider, fetched, inserted, duplicates, skipped, state}`. Returns
  HTTP 503 with sanitized provider state when the provider is not healthy.
- `GET /api/dns/events` — supports `limit`, `offset`, `device_id`, `blocked`,
  `source`; each row includes `domain`, `category`, `timestamp`, `query_type`,
  `client`, `client_name`, `reason`, `rules`, `upstream`, `source`, `confidence`.
- `POST /api/dns/events` — legacy manual event insert (`source=manual`).

## Analytics

- `GET /api/dns/analytics/summary?device_id=&since=` — `total`,
  `unique_domains`, `by_category`, `blocked`, `allowed`,
  `blocking_percentage` (null when no event has a known status),
  `unknown_blocked_status`, `top_domains`, `top_blocked_domains`, `by_client`,
  `by_source`, `timeline`, `category_evidence`.
- `GET /api/dns/analytics/domains?limit=`, `GET /api/dns/analytics/devices`,
  `GET /api/dns/analytics/clients`.

Missing blocked information is reported separately from explicit zero; a
blocking percentage is computed only over events with known blocked status.

## Audit, policy, consent, recovery

- `POST /api/audits/run`, `GET /api/audits`, `GET /api/audits/{id}`, `GET /api/audits/{id}/findings`.
- `POST /api/policies/plan?audit_id=`, `POST /api/policies/dry-run`, `GET /api/policies/dry-run/{id}`, `GET /api/policies/dry-run/{id}/impact`.
- `POST /api/policies/{id}/approve?plan_id=&confirm=true` — explicit confirmation required.
- `POST /api/policies/{id}/apply` — only for approved policies and only when
  `NETRA_DNS_ENFORCEMENT_ENABLED=true` with a configured provider.
- `GET /api/policies/{id}/execution`, `GET /api/policies/{id}/approval`, `GET /api/policies/{id}/rollback-status`.
- `GET /api/verification/policy/{id}` — checks real provider query-log evidence.
- `POST /api/snapshots`, `GET /api/snapshots`, `GET /api/snapshots/{id}`,
  `POST /api/snapshots/{id}/rollback?confirm=true` — restores the previous
  provider user-rule list.
- `GET /api/backend/capabilities`, `GET /api/backend/health`,
  `GET /api/enforcement/status`, `GET /api/recovery/status`.

`/api/dns/sources/status` is retained for compatibility and now reports real
provider state in additive fields.

## Live overview, diagnostics and policy management

- `GET /api/dashboard/summary?subnet=` — aggregates real device, DNS, provider,
  privacy-audit, enforcement-readiness and host-bandwidth facts. It does not
  claim router-wide protection.
- `GET /api/bandwidth/interfaces`, `GET /api/bandwidth/status?interface=`,
  `POST /api/bandwidth/sample?interface=&interval_ms=1000`,
  `GET /api/bandwidth/history?interface=&limit=` — bounded host-local
  `/proc/net/dev` sampling. Scope is always `netra-host-interface`.
- `GET /api/discovery/status` — bounded scan coverage and last-scan timestamp.
- `GET /api/enforcement/readiness` — gateway/interface, required permissions,
  supported and unsupported modes, safety warnings, snapshot count and
  provider/network readiness without changing settings.
- `GET /api/diagnostics/adguard` — provider configuration/reachability/auth
  state, filtering rules, statistics, query-log evidence, selected-client
  identification and independent router DHCP/DNS verification status.
- `GET /api/dns/events?domain=&client=&...` and
  `POST /api/dns/providers/filtering/refresh?confirm=true` — event filtering and
  explicit provider reload where supported.
- `POST /api/dns/providers/filtering/rules` accepts actions `block`, `unblock`,
  `allow` and `remove`. All require `confirm: true`.
- `POST /api/policies`, `GET /api/policies/{id}`,
  `PUT /api/policies/{id}`, `DELETE /api/policies/{id}?confirm=true` — saved
  device policy CRUD. `config_json` stores only genuinely supported DNS controls.
- `POST /api/policies/preview?audit_id=` — non-persistent policy drafts. It does
  not save policies or apply changes.
- `POST /api/snapshots/from-provider` captures real provider user rules as a
  configuration snapshot; it is not a database backup.
- `GET /api/privacy/score?subnet=&device_id=&since=` and
  `POST /api/privacy/policies/preview` — evidence-backed score and dry-run
  policy drafts. No DNS observations are reported separately from no risk.
