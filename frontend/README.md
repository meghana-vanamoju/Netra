# Netra frontend

Responsive React + TypeScript dashboard built with Vite. The overview reads device inventory, DNS analytics, saved audit results, and backend health from the existing Netra API. Device inventory adds local search, classification/source filters, sortable columns, pagination, and device details. LAN discovery, privacy audits, policy planning, and dry-run evaluations are explicit, user-triggered actions. Audit runs evaluate stored inventory/DNS records; policy planning and dry-run save backend records. None of these actions applies network configuration. The UI does not create demo data.

## Requirements

- Node.js 18 or newer
- npm
- Netra backend running locally or at a configured API URL

## Setup and run

```bash
npm install
npm run dev
```

Vite serves the frontend at `http://localhost:5173`. Start the API separately from the repository root:

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --reload
```

## Configuration

The API client defaults to `http://localhost:8000`. To use another backend, create `frontend/.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

Restart Vite after changing environment variables. The backend must allow the frontend's origin through CORS.

## Dashboard data

The overview uses these read-only endpoints:

- `GET /api/health`
- `GET /api/db/health`
- `GET /api/devices?limit=200`
- `GET /api/dns/analytics/summary`
- `GET /api/audits`
- `GET /api/audits/{audit_id}`
- `GET /api/audits/{audit_id}/findings`
- `GET /api/backend/capabilities`
- `GET /api/classifications`
- `POST /api/devices/{device_id}/classify` (only after the user requests recalculation in device details)
- `POST /api/discovery/run?subnet={cidr}` (only after the user starts a scan)
- `GET /api/discovery/results` (only after a scan is submitted)

If no saved audit exists, the dashboard says so; it does not run one. The DNS backend capability is labeled as configuration only and is not presented as active protection. API failures appear in the relevant dashboard panels with the backend error or connection guidance.

The Privacy Audit page can run the backend-supported network or single-device
audit scopes after explicit user submission. It shows saved reports and the
finding evidence returned by the API. Audit history has no failed-run records
or target-device metadata, and the UI does not infer a compromise verdict or
risk score.

The Policy Planning page explicitly generates persistent policy proposals from
a saved audit and can create a persistent dry-run plan for selected policies.
It does not offer policy approval, application, or enforcement. The backend
does not expose per-policy rationale or targets, durable audit-to-policy
linkage, or per-policy dry-run attribution; the UI labels those details as
unavailable instead of inferring them. Repeating policy planning can create
additional records; the backend does not guarantee deduplication.

The Enforcement & Recovery page reads backend configuration, saved policy
status, verification, execution and rollback status, recovery status, and saved
snapshot history/details. It does not create snapshots or trigger approval,
policy application, rollback, or recovery. A configured backend does not mean
traffic is protected: policy application and snapshot rollback are not
implemented, verification reports `not_verified`, and recovery status is a
fixed backend response. See `../docs/FRONTEND_API_CONTRACT.md` for exact
schemas and limitations.

Discovery is synchronous, does not report progress, and probes at most 64
addresses using the backend host's local network context. Its results are
in-memory on the backend; a zero-result response does not prove that a network
has no devices or that discovery permissions were sufficient. The UI accepts
private IPv4 subnets no larger than `/16` for this synchronous scanner.

## Build

```bash
npm run build
npm run preview
```

There is not yet a frontend test runner configured in this scaffold.
