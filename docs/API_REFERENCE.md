# API Reference

All paths are relative to `http://127.0.0.1:8000` unless `VITE_API_BASE_URL`
says otherwise. No built-in authentication is provided; protect the backend
with your own reverse proxy if it is exposed beyond loopback.

## Core

- `GET /api/health` — service health.
- `GET /api/db/health` — `SELECT 1` database check.
- `GET /api/devices`, `POST /api/devices`, `GET /api/devices/{id}`.
- `GET /api/discovery/results`, `POST /api/discovery/run`, router discovery routes.
- `GET /api/classifications/...`.

## DNS provider and query data

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
