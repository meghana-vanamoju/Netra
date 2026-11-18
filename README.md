# Netra — Network Privacy & Device Guardian

> **Tagline:** See your network clearly. Protect it safely.

**Track:** Home Router — Clean Connected Devices Hackathon

Netra is a privacy-first network guardian for home routers. It aims to give users clear visibility into the devices on their local network, their DNS activity, and the trackers, telemetry, and advertisements those devices generate — without silently changing anything.

Modern home networks contain dozens of connected devices, many of which communicate in the background with unknown endpoints. Users rarely have a simple, trustworthy way to see what is happening or to make safe, reversible privacy improvements. Netra addresses this gap with read-only auditing by default, explicit consent before any change, dry-run previews, and rollback.

## Vision and Objectives

Netra aims to:

- Discover and inventory devices on a local network.
- Audit network and DNS activity.
- Identify known advertisements, trackers, telemetry, and suspicious domains.
- Classify privacy risks and device components.
- Recommend safe, reversible privacy improvements.
- Measure network and privacy improvements before and after changes.
- Provide an accessible, multilingual dashboard.

## Features

### Implemented

- FastAPI backend foundation.
- Device inventory, discovery, and classification APIs.
- DNS analytics, privacy audits, policy planning, enforcement lifecycle, snapshots, recovery, and backend capability APIs.
- Real AdGuard Home query-log/statistics integration with authenticated API access, bounded idempotent sync, provider health states, and Pi-hole compatibility.
- Evidence-based domain categorization (advertising, tracking/analytics, telemetry, social, CDN, essential, unknown) with category confidence and source labels.
- React + TypeScript + Vite frontend with a responsive live dashboard and dedicated pages for DNS protection, privacy audit, device policies, enforcement readiness, host-local bandwidth, configuration snapshots, and AdGuard diagnostics.
- Frontend/backend separation with dedicated backend domain modules.

### Not implemented / explicitly out of scope

- Automatic router DHCP/DNS changes or privilege escalation. Netra does not
  modify router settings.
- Router-wide or client-level protection claims without independent router
  DHCP/DNS evidence and client query-log evidence.
- Full database backups. Only provider configuration snapshots are available.
- Internet-access scheduling and device internet-disable controls; the backend
  does not expose these as supported modes.
- Router-wide bandwidth accounting. Bandwidth is host-local
  (`netra-host-interface`) from `/proc/net/dev`.

The dashboard foundation presents existing backend data and connection status. It does not run audits automatically or claim that DNS protection is active.

## Architecture

### Current Foundation

- **Frontend:** React, TypeScript, Vite.
- **Backend:** FastAPI (Python).
- **Persistence:** SQLite.
- **UI styling:** Responsive CSS and shared design tokens.
- **Charts:** Not currently used; dashboard summaries use lightweight CSS.
- **Localization:** i18next with English, Telugu, Hindi, Tamil, and Kannada (planned).

### Intended Module Boundaries

- `frontend/` — React + TypeScript + Vite dashboard.
- `backend/` — FastAPI application and API routes.
- `backend/discovery/` — LAN device discovery.
- `backend/dns/` — DNS event analytics.
- `backend/dns_filter/` — DNS filtering integration (planned).
- `backend/audit/` — Privacy audit engine.
- `backend/policy/` — Policy planning and enforcement support.
- `backend/benchmarking/` — Before/after measurements (planned).
- `backend/db/` — SQLite persistence.

Frontend communicates with the backend over HTTP (JSON). DNS filtering will integrate an established filtering engine/provider rather than reimplementing DNS.

The frontend dashboard foundation is implemented; remaining management screens and localization are planned.

## Safety and Privacy

Netra is designed with the following guarantees:

- Read-only auditing by default.
- No silent router configuration changes.
- Explicit user consent before applying any network policy.
- Dry-run preview before any change.
- Reversible changes wherever supported.
- Configuration snapshots and rollback.
- Never modify safety-critical or irreversible router/system components.
- No credentials, router passwords, or sensitive network data committed to Git.
- No claim that DNS filtering protects against every advertisement or tracker.
- Clear distinction between actual measurements and demo/sample data.

## Audit and Benchmarking

Planned audit workflow:

1. Discover.
2. Inventory.
3. Audit/classify.
4. Generate report.
5. Dry-run.
6. Consent.
7. Apply approved policy.
8. Benchmark.
9. Rollback if necessary.

Planned metrics:

- DNS query counts and domain categories.
- Blocked/allowed requests where observable.
- DNS/network latency.
- Privacy risk indicators.
- Device inventory changes.
- Battery metrics only if an actual trustworthy measurement source exists.

## Dashboard and Localization

Implemented dashboard foundation:

- Device inventory.
- DNS activity and analytics.
- Privacy/audit summaries.
- Backend and database health.
- Responsive desktop, tablet, and mobile layouts.

Remaining dashboard work:

- Policy, enforcement, and recovery management screens.
- Before/after benchmarks and report export.
- Languages: English, Telugu, Hindi, Tamil, Kannada.

## Repository Structure

Current structure:

```
Netra/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── test_health.py
├── frontend/
│   ├── README.md
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
│       ├── api.ts
│       ├── App.tsx
│       ├── main.tsx
│       ├── styles.css
│       └── types.ts
├── .gitignore
└── README.md
```

Additional backend routes and domain modules live under `backend/`; API details are documented in `docs/FRONTEND_API_CONTRACT.md`.

## Getting Started

### Clone

```bash
git clone https://github.com/meghana-vanamoju/Netra.git
cd Netra
```

### Backend Setup

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8084
```

API available at `http://127.0.0.1:8084`. Health check: `GET /api/health`.

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend available at `http://localhost:5173`.

Set `VITE_API_BASE_URL` in the frontend environment to use a different backend (default: `http://127.0.0.1:8084`). See [frontend/README.md](frontend/README.md) for configuration and execution details.

### Tests

```bash
cd backend
python3 -m pytest -q
cd ../frontend
npm test
npm run build
```

### LAN Discovery and live inventory

LAN Discovery is manual and read-only. The backend accepts only authorized
private IPv4 subnets, probes at most 64 hosts with at most eight concurrent
single-packet ICMP probes, and applies a 1.25-second per-host process deadline
plus a 12-second overall scan deadline. Timed-out work returns partial results
when possible. Results include scan duration, attempted probes, responding
hosts, timeouts, probe errors, and partial-result status.

Only successful ICMP replies and newly observed Linux neighbor entries are
reported. Existing unchanged neighbor-cache entries are not treated as fresh
discoveries. MAC addresses come only from complete neighbor entries; reverse
DNS is disabled by default, and hostnames and vendors remain unknown unless
another configured source provides evidence. See
[Discovery API details](docs/API_REFERENCE.md#lan-discovery) and the
[hardware benchmark](docs/HARDWARE_TEST_RESULTS.md#bounded-concurrent-discovery-benchmark).

### Real DNS provider (AdGuard Home)

Set provider configuration in the **backend** environment (never in frontend
code or Git). The local lab compose file maps AdGuard Home's web UI to port
`3001`:

```bash
export NETRA_ADGUARD_API_URL=http://127.0.0.1:3001
export NETRA_ADGUARD_USERNAME='<AdGuard Home user>'
export NETRA_ADGUARD_PASSWORD='<secret>'
export NETRA_DNS_BACKEND=adguard          # optional when only AdGuard is configured
export NETRA_DNS_ENFORCEMENT_ENABLED=true # opt-in only; omit for read-only monitoring
```

Then:

```bash
curl -s http://127.0.0.1:8084/api/dns/providers/status
curl -s -X POST http://127.0.0.1:8084/api/dns/events/sync
curl -s http://127.0.0.1:8084/api/dns/analytics/summary
```

Read-only monitoring works without `NETRA_DNS_ENFORCEMENT_ENABLED`. Policy
application always requires a dry run and explicit approval, and rollback is
recorded as a configuration snapshot. See
[AdGuard Home integration](docs/ADGUARD_HOME_INTEGRATION.md) for limits and
hardware evidence.

## API

### Implemented

- `GET /api/health` and `GET /api/db/health` — service and database health.
- `GET /api/devices?limit=200` — dashboard device inventory (backend maximum per request: 200).
- `GET /api/dns/analytics/summary` — DNS event and category totals, including blocked/allowed metrics and time buckets.
- `GET /api/dns/providers/status`, `GET /api/dns/providers/statistics`, `GET /api/dns/providers/filtering`, `POST /api/dns/events/sync` — real provider state and bounded, idempotent query retrieval.
- `GET /api/audits`, `GET /api/audits/{audit_id}`, and `GET /api/audits/{audit_id}/findings` — latest saved audit and findings; dashboard reads these without starting an audit.
- `GET /api/backend/capabilities` — DNS backend configuration status, not proof of active enforcement.

### Planned

- Full device, DNS, audit, policy, and recovery management screens.
- Localization and benchmarking.

## Roadmap

1. Foundation — project scaffolding, health endpoint. (done)
2. Persistence — SQLite models and migrations.
3. Device inventory — discovery and classification.
4. DNS analytics — query logging and categorization.
5. Classification and audit — risk scoring and reports.
6. Policy planning, consent, and rollback — dry-run, apply, snapshot, revert.
7. Dashboard and localization — full UI with 5 languages.
8. Benchmarking — before/after measurements.
9. Documentation, video, and demo — final deliverables.

## Hackathon Deliverables

- Source repository.
- Working demo.
- Safety report.
- Before/after measurements.
- Programmatic video tutorial.
- Social documentation.
- Live demonstration workflow.

## Evaluation Alignment

- Ads, telemetry, bloat, security — 25%.
- UI/UX and Indic languages — 25%.
- Performance/network improvements — 20%.
- Social engagement — 20%.
- Programmatic video/documentation — 10%.

## Contributing

- Work on feature branches or small commits on `main` per project workflow.
- Run relevant tests before committing.
- Use conventional commit messages.
- Do not commit secrets, credentials, or sensitive network data.

## Testing

```bash
cd backend && python3 -m pytest -q
```

Frontend test commands will be added once the test framework is configured.

## Safety Disclaimer

Netra is an auditing and planning tool. It does not perform destructive router changes by default. Any policy application requires explicit user consent and a dry-run preview. DNS filtering cannot guarantee protection against all advertisements or trackers. Measurements should be clearly labeled as actual or demo/sample.

## License

No license file is present in the repository at this time. License to be added.
