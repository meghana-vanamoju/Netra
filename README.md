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
- `/api/health` endpoint returning service status.
- React + TypeScript + Vite frontend scaffold with a basic dark dashboard placeholder.
- Backend test for the health endpoint.
- Project structure separating frontend, backend, and (planned) discovery, DNS filtering, audit, policies, benchmarking, and rollback modules.

### Planned

- LAN device discovery and inventory.
- Device classification: essential, optional, distracting, privacy-risk.
- DNS analytics and domain categorization.
- Audit reports.
- Dry-run policy planner.
- Explicit-consent policy application.
- Safe DNS filtering integration (via an established filtering engine/provider).
- Configuration snapshots and rollback.
- Before/after benchmarking.
- Multilingual dashboard (English, Telugu, Hindi, Tamil, Kannada).
- Exportable reports.

No planned feature is currently operational.

## Architecture

### Current Foundation

- **Frontend:** React, TypeScript, Vite.
- **Backend:** FastAPI (Python).
- **Persistence:** SQLite (planned).
- **Charts:** Recharts (planned).
- **UI styling:** Tailwind CSS (planned).
- **Localization:** i18next with English, Telugu, Hindi, Tamil, and Kannada (planned).

### Intended Module Boundaries

- `frontend/` — React + TypeScript + Vite dashboard.
- `backend/` — FastAPI application and API routes.
- `backend/discovery/` — LAN device discovery (planned).
- `backend/dns_filter/` — DNS filtering integration (planned).
- `backend/audit/` — Audit and classification (planned).
- `backend/policies/` — Policy planning and consent (planned).
- `backend/benchmarking/` — Before/after measurements (planned).
- `backend/rollback/` — Snapshots and rollback (planned).
- `backend/db/` — SQLite persistence (planned).

Frontend communicates with the backend over HTTP (JSON). DNS filtering will integrate an established filtering engine/provider rather than reimplementing DNS.

All components beyond the foundation are marked as planned.

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

Planned dashboard surfaces:

- Device inventory.
- DNS activity and analytics.
- Privacy/audit summaries.
- Policy status.
- Before/after benchmarks.
- Configuration snapshot and rollback history.
- Languages: English, Telugu, Hindi, Tamil, Kannada.
- Responsive and accessible UI.

## Repository Structure

Current structure:

```
Netra/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── test_health.py
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx
│       └── main.tsx
├── .gitignore
└── README.md
```

Planned additions (not yet present): `backend/db/`, `backend/discovery/`, `backend/dns_filter/`, `backend/audit/`, `backend/policies/`, `backend/benchmarking/`, `backend/rollback/`, `tests/`, `docs/`.

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
python3 -m uvicorn main:app --reload
```

API available at `http://localhost:8000`. Health check: `GET /api/health`.

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend available at `http://localhost:5173`.

Note: Tailwind CSS, Recharts, and i18n are planned and not yet installed.

### Tests

```bash
cd backend
python3 -m pytest -q
```

## API

### Implemented

- `GET /api/health` — returns `{"status": "ok", "service": "netra-backend", "version": "0.1.0"}`.

### Planned

- Device inventory endpoints.
- DNS analytics endpoints.
- Audit report endpoints.
- Policy planning/consent endpoints.
- Benchmarking endpoints.
- Snapshot/rollback endpoints.

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
