# AdGuard Home DNS Integration (Milestone 9.0)

## Verified environment

| Field | Observed |
|---|---|
| Image | `adguard/adguardhome:v0.107.50` |
| Reported version | `v0.107.50` (`GET /control/status`) |
| Web API | `http://127.0.0.1:3001` (compose maps `3001:80`) |
| DNS listener | UDP `0.0.0.0:53`, active in the running container |
| Authentication | HTTP Basic; username/password from backend environment |
| Query log | `GET /control/querylog?limit=&offset=`, enabled |
| Statistics | `GET /control/stats`, enabled |
| Filtering | `GET /control/filtering/status`, `POST /control/filtering/set_rules` |
| Query-log fields used | `question.name`, `question.type`, `client`, `client_info.name`, `time`, `status`, `reason`, `rules`, `upstream`, `answer`, `cached` |

The lab initially had a bcrypt password hash but no recoverable plaintext. A
new **local-only** lab password was generated and is kept outside Git in the
backend environment; no credential value is recorded in this repository. The
container was restarted with the existing configuration and data volumes.

## Configuration

```text
NETRA_ADGUARD_API_URL=http://127.0.0.1:3001
NETRA_ADGUARD_USERNAME=<user>
NETRA_ADGUARD_PASSWORD=<secret>
NETRA_DNS_BACKEND=adguard
NETRA_ADGUARD_TIMEOUT=5
NETRA_ADGUARD_CONNECT_TIMEOUT=3
NETRA_ADGUARD_MAX_EVENTS=500
NETRA_ADGUARD_PAGE_SIZE=100
NETRA_DNS_ENFORCEMENT_ENABLED=true   # optional, opt-in only
```

`NETRA_ADGUARD_DNS_URL` overrides `NETRA_ADGUARD_API_URL` for DNS monitoring if
both are set. The legacy router-inventory route still uses
`NETRA_ADGUARD_API_URL` with an exact router-IP hostname match.

## Behavior

- `AdGuardHomeAdapter.health()` probes the real status, query-log, statistics,
  and filtering endpoints. HTTP 401/403 → `unauthorized`, 404 →
  `unsupported_api`, 5xx → `provider_unavailable`, connect errors →
  `unreachable`, timeouts → `timeout`, invalid JSON → `malformed_response`.
- `fetch_queries()` walks bounded pages, normalizes RFC3339 nanosecond
  timestamps, validates domains, and deduplicates by a stable fingerprint of
  timestamp + domain + query type + client + reason.
- `POST /api/dns/events/sync` stores only new rows. Repeating it does not
  duplicate events or delete older records. `source` is `adguard-home` (or
  `pihole`), while manually posted events use `manual` and seeded fixtures use
  `synthetic-demo`.
- A query with a `Filtered*` reason is recorded as blocked. If the provider
  omits filtering data, `blocked` is null and the summary reports it under
  `unknown_blocked_status` rather than treating it as allowed.
- Classification uses conservative suffix rules with evidence and confidence.
  Unmatched domains remain `Unknown`; no domain is called malicious based only
  on a rule match.

## Domain categories

| Category | Example rule evidence |
|---|---|
| Advertising | `doubleclick.net`, `googlesyndication.com` |
| Tracking/Analytics | `google-analytics.com`, `segment.io` |
| Telemetry | `sentry.io`, `telemetry.microsoft.com` |
| Social media | `facebook.com`, `linkedin.com` |
| Content delivery | `cdn.jsdelivr.net`, `cloudfront.net` |
| Essential services | `microsoft.com`, `apple.com`, `google.com` (excluded from blocking plans) |
| Unknown | no matching rule |

Longest suffix wins. Confidence describes only the local rule match, not a
security verdict.

## Enforcement boundaries

- Default state is read-only. `NETRA_DNS_ENFORCEMENT_ENABLED` must be set
  explicitly before any rule is written.
- A policy must be dry-run, approved with `confirm=true`, and have validated
  target domains. Essential suffixes are excluded.
- Apply adds exact user rules (`||domain^`) to **the configured AdGuard lab**,
  records consent metadata, and creates a configuration snapshot of the prior
  user-rule list.
- `GET /api/verification/policy/{id}` requires real query-log evidence of a
  filtered response; an API success alone is not verification.
- `POST /api/snapshots/{id}/rollback?confirm=true` restores the exact prior
  user-rule list and records a `rolled_back` execution.
- The personal router's DNS settings were not changed. No traffic was
  redirected and no system-wide ad-blocking claim is made.

## Limitations

- AdGuard Home's query log is point-in-time and bounded by its own retention;
  Netra cannot reconstruct events older than the provider retains.
- `client` may be an IP, hostname, or empty string. Netra links by exact client
  IP first, then client name; unmatched events remain device-less.
- Pi-hole compatibility is implemented for the v6 `/api/queries` token API;
  older v5 endpoints are not yet supported. Its statistics/filtering
  capabilities are reported as unsupported rather than inferred.
- Default AdGuard filter lists may also block a controlled test domain. Rule
  causality is established from the exact user-rule snapshot plus filtered
  query-log evidence, not from an HTTP 200 alone.
- No frontend redesign was performed. The additive TypeScript client contract
  for Copilot is documented in [FRONTEND_API_CONTRACT.md](FRONTEND_API_CONTRACT.md).
