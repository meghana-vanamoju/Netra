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
- Connected-device hotspot status, non-mutating plans, loopback-only consent-gated network controls (nftables apply disabled by default)
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
7. Open Connected Devices and show the detected hotspot/client states and
   non-mutating plan. Do not apply a real network change during a general demo.
8. Show theme switching.

## Live vs mocked
- Backend APIs are live. DNS-policy enforcement and hotspot-client enforcement
  are separate features. Hotspot-client enforcement can change only this Linux
  host's nftables state after deliberate opt-in and confirmation.
- Frontend uses live backend when available.

## Limitations
- No active DNS protection.
- No real router configuration changes.
- Hotspot client controls are Linux-only, disabled by default, and not
  validated against physical clients. See
  [Network enforcement](NETWORK_ENFORCEMENT.md).

## Security/consent
- Read-only by default.
- Explicit confirmation required for control application; plan/apply endpoints
  accept loopback clients only.
- Do not enable actual enforcement except on a disposable test host. The
  backend has no general authentication system.
- No credentials stored.
