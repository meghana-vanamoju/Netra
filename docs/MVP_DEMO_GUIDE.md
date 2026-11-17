# Netra MVP Demo Guide

## What Netra does
Netra is a privacy-first network guardian for home routers with read-only auditing by default.

## Working features
- Device inventory API
- Discovery (read-only)
- Classification
- DNS analytics
- Privacy audit reports
- Policy dry-run planner
- Consent/enforcement stubs (backend unavailable by default)
- Snapshots/rollback (backend unavailable)
- Light/Dark/System themes

## Setup
Backend:
cd backend && python3 -m pip install -r requirements.txt && python3 -m uvicorn main:app --reload

Frontend:
cd frontend && npm install && npm run dev

## Demo sequence (3-5 min)
1. Open dashboard.
2. Show device inventory.
3. Run discovery.
4. Show DNS analytics.
5. Run privacy audit.
6. Show policy dry-run impact.
7. Show consent requirement and backend unavailable.
8. Show theme switching.

## Live vs mocked
- Backend APIs are live; no real router enforcement.
- Frontend uses live backend when available.

## Limitations
- No active DNS protection.
- No real router configuration changes.
- No real enforcement backend configured.

## Security/consent
- Read-only by default.
- Explicit consent required for policy application.
- No credentials stored.
