# Netra frontend

Responsive React + TypeScript dashboard built with Vite. The overview reads device inventory, DNS analytics, saved audit results, and backend health from the existing Netra API. It does not create demo data, run audits, or apply policies.

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

If no saved audit exists, the dashboard says so; it does not run one. The DNS backend capability is labeled as configuration only and is not presented as active protection. API failures appear in the relevant dashboard panels with the backend error or connection guidance.

## Build

```bash
npm run build
npm run preview
```

There is not yet a frontend test runner configured in this scaffold.
