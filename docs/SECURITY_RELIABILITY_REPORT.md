# Security & Reliability Report

## Scope
Backend API, persistence, discovery, DNS analytics, audit, policy, snapshots.

## Findings
- No real backend enforcement configured (by design).
- CORS restricted to local dev origins.
- Read-only by default.

## Tests
- 31 backend tests passed.
- Compileall passed.

## Remaining risks
- No authentication/authorization layer.
- No real DNS backend configured.
- Demo mode must be clearly labeled.
