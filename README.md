# Netra — Network Privacy & Device Guardian

**See your network clearly. Protect it safely.**

[![Backend Tests](https://img.shields.io/badge/Backend-299%20passed-success)]()
[![Frontend Tests](https://img.shields.io/badge/Frontend-26%20passed-success)]()
[![Build](https://img.shields.io/badge/Frontend%20Build-Passing-success)]()
[![Platform](https://img.shields.io/badge/Platform-Linux-blue)]()
[![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript-blue)]()
[![Backend](https://img.shields.io/badge/Backend-FastAPI-green)]()

**Netra** is a privacy-first home network monitoring and management platform designed to give users visibility into connected devices, DNS activity, network behavior, and device-level Internet access.

It combines network discovery, DNS analytics, AdGuard Home integration, privacy insights, and controlled per-device Internet access management through a centralized dashboard.

Netra follows a safety-first approach: network inspection is read-only by default, while changes require explicit user confirmation, controlled execution, and verification.

---

## Project Goal

To develop an open-source, privacy-first home network guardian that enables users to discover connected devices, monitor DNS activity, understand network privacy risks, and securely control Internet access for individual devices through a centralized dashboard.

## The Problem

Modern home networks contain multiple connected devices, including smartphones, laptops, smart TVs, and IoT devices.

Users often have limited visibility into:

- Which devices are connected to their network.
- What DNS requests those devices generate.
- Which domains are associated with advertising, tracking, and telemetry.
- Which devices should have Internet access.
- Whether a network restriction has actually been applied.

Traditional router interfaces often provide limited device-level visibility and control.

Netra aims to make these operations more understandable, transparent, and manageable.

---

## Key Features

### 1. Connected Device Discovery

- Discover devices connected to supported local networks.
- Identify devices using IP addresses and MAC addresses.
- Correlate Wi-Fi station information with neighbor-table observations.
- Display connection and identity validation states.
- View connected devices through a centralized inventory.
- Perform bounded, read-only LAN discovery.

### 2. Per-Device Internet Access Control

Netra provides device-specific Internet access management for supported Linux hotspot environments.

Features include:

- Select an individual connected device.
- Generate a dry-run restriction plan.
- Review the proposed operation.
- Explicitly confirm the restriction.
- Block Internet access for the selected device.
- Verify the resulting firewall state.
- Restore Internet access when required.
- Inspect enforcement state and operation history.

The implementation uses Linux nftables and a restricted privileged helper.

**Physical demonstration:** Netra was tested using multiple phones connected to a Linux-hosted Wi-Fi hotspot.

The demonstration included:
1. Detecting connected devices.
2. Selecting Phone A for Internet restriction.
3. Applying and verifying the restriction.
4. Confirming Phone A lost Internet access.
5. Confirming Phone B retained Internet access.
6. Restoring Phone A's Internet access.

This demonstrates selective device-level access control in the tested environment.

### 3. DNS Monitoring and Analytics

Netra integrates with AdGuard Home to provide DNS visibility.

Features include:

- Retrieve DNS query logs.
- Synchronize provider events.
- Display blocked and allowed DNS requests.
- Categorize domains using available evidence.
- Display DNS analytics and time-based summaries.
- Inspect provider health and statistics.
- Correlate eligible AdGuard events with local dnsmasq journal records.
- Preserve ambiguous or unmatched attribution rather than inventing device identities.

### 4. Privacy Intelligence

Netra supports evidence-based domain categorization.

Categories include:

- Advertising
- Tracking and analytics
- Telemetry
- Social
- CDN
- Essential services
- Unknown

Classification includes confidence and source information where available.

Domain classification should not be interpreted as proof that every request is malicious or unwanted.

### 5. Privacy Auditing and Device Policies

- Device inventory and classification.
- Privacy audit workflows.
- Findings and risk indicators.
- Policy planning.
- Dry-run previews.
- Explicit confirmation before supported changes.
- Audit history and recovery-related workflows.

### 6. Network Monitoring

- Uplink status.
- Active hotspot status.
- Connected device count.
- Interface information.
- Host-local bandwidth observations.
- Backend and database health.
- Enforcement readiness and verification states.

### 7. Snapshots and Recovery

- Configuration snapshot support.
- Enforcement state inspection.
- Device-specific recovery snapshots.
- Checksum validation for helper-managed recovery state.
- Targeted restoration and rollback mechanisms.

These features do not constitute full operating-system or router backups.

### 8. Dashboard and User Interface

The Netra dashboard is built using React and TypeScript.

It provides:

- Network overview.
- Connected Devices page.
- DNS analytics.
- Privacy audit views.
- Device policies.
- Network enforcement controls.
- AdGuard diagnostics.
- Host telemetry.
- Configuration and recovery views.
- Responsive layouts and clear operation states.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React |
| Language | TypeScript |
| Frontend tooling | Vite |
| Backend | Python |
| API framework | FastAPI |
| Database | SQLite |
| DNS integration | AdGuard Home |
| DNS correlation | dnsmasq / NetworkManager journal |
| Firewall enforcement | Linux nftables |
| Privileged operations | Python Unix socket helper |
| Service management | systemd |
| Containerization | Docker Compose |
| Backend testing | Pytest |
| Frontend testing | Vitest |

---

## System Architecture

Netra separates its dashboard, backend services, DNS integrations, and privileged network operations.

```text
                  USER
                   |
                   v
          React + TypeScript UI
                   |
                   v
             FastAPI Backend
                   |
        +----------+-----------+
        |          |           |
        v          v           v
     Device      DNS        Privacy
   Discovery   Analytics     Audits
        |          |
        |          v
        |      AdGuard Home
        |
        v
   Network Topology
        |
        v
   Network Control API
        |
        v
   Restricted Helper Client
        |
        v
     Unix Socket
        |
        v
  Privileged Helper
        |
        v
     nftables
        |
        v
 Linux Hotspot Network
```

### Privileged Helper Architecture

The backend does not require `CAP_NET_ADMIN`.

Instead, a dedicated systemd-managed helper performs narrowly scoped firewall operations.

The backend communicates with the helper through a Unix domain socket using a bounded JSON protocol.

The helper provides:

- Caller UID/GID authorization.
- Strict request validation.
- Device identity validation.
- Interface and table restrictions.
- Serialized firewall operations.
- State inspection.
- Apply, restore, verify, and rollback operations.
- Protected recovery snapshots.

Only the helper is intended to hold the required network-administration capability.

Systemd socket activation is not supported by the current helper implementation. The helper creates and manages its own Unix socket.

---

## Security and Privacy Principles

Netra is designed around the following principles:

1. Read-only inspection by default.
2. No silent router configuration changes.
3. Explicit confirmation before applying network restrictions.
4. Dry-run previews before supported changes.
5. Restricted privileged operations.
6. Device identity validation before enforcement.
7. Verification before reporting successful enforcement.
8. Recovery and rollback support.
9. Loopback-only authorization for sensitive network-control API operations.
10. No credentials or sensitive network information committed to Git.

**Important:** Loopback-only API access is an access restriction, not a complete authentication system.

Netra does not claim universal router-wide protection or guarantee that all advertisements and trackers can be blocked.

---

## Repository Structure

```text
Netra/
├── backend/
│   ├── main.py
│   ├── api_dns.py
│   ├── api_network_control.py
│   ├── network_enforcement_helper.py
│   ├── db/
│   ├── dns/
│   │   └── journal.py
│   ├── discovery/
│   ├── network_enforcement/
│   │   ├── commands.py
│   │   ├── config.py
│   │   ├── constants.py
│   │   ├── errors.py
│   │   ├── identity.py
│   │   ├── nftables.py
│   │   ├── privileged_client.py
│   │   ├── privileged_protocol.py
│   │   ├── service.py
│   │   ├── target.py
│   │   └── topology.py
│   └── test_*.py
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── ConnectedDevicesPage.tsx
│   │   ├── App.tsx
│   │   ├── api.ts
│   │   ├── styles.css
│   │   └── types.ts
│   └── package.json
│
├── deploy/
│   ├── README.md
│   ├── netra-backend-helper.conf
│   └── netra-network-helper.service
│
├── docs/
│   ├── API_REFERENCE.md
│   ├── ARCHITECTURE.md
│   ├── INSTALLATION.md
│   ├── MVP_DEMO_GUIDE.md
│   └── NETWORK_ENFORCEMENT.md
│
├── docker-compose.adguard.yml
├── .gitignore
└── README.md
```

---

## Getting Started

### Prerequisites

- Linux environment (Debian-based distribution recommended).
- Python 3.
- Node.js and npm.
- Git.
- Docker and Docker Compose for the AdGuard Home deployment.
- nftables for supported network enforcement.

### 1. Clone the repository

```bash
git clone https://code.swecha.org/Meghana_Vanamoju/netra.git

cd Netra
```

### 2. Backend setup

```bash
cd backend

python3 -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt
```

Start the backend:

```bash
python -m uvicorn main:app \
  --app-dir . \
  --host 127.0.0.1 \
  --port 8084
```

Backend:

`http://127.0.0.1:8084`

API documentation:

`http://127.0.0.1:8084/docs`

### 3. Frontend setup

Open another terminal:

```bash
cd Netra/frontend

npm install

npm run dev
```

Frontend:

`http://localhost:5173`

To configure another backend address, set:

```text
VITE_API_BASE_URL=http://127.0.0.1:8084
```

### 4. AdGuard Home setup

Netra supports AdGuard Home integration through Docker Compose.

Review the configuration:

```bash
cat docker-compose.adguard.yml
```

Configure provider credentials through backend environment variables.

```bash
export NETRA_ADGUARD_API_URL=http://127.0.0.1:3001
export NETRA_ADGUARD_USERNAME='<your-username>'
export NETRA_ADGUARD_PASSWORD='<your-password>'
export NETRA_DNS_BACKEND=adguard
```

Never commit actual credentials or `.env` files.

Refer to `docs/INSTALLATION.md` and `docs/API_REFERENCE.md` for additional configuration.

---

## Network Enforcement Deployment

Per-device Internet access control requires a supported Linux hotspot environment.

The backend and helper must be configured separately.

Deployment examples are provided in:

```text
deploy/
```

Read:

- `deploy/README.md`
- `deploy/netra-network-helper.service`
- `deploy/netra-backend-helper.conf`
- `docs/NETWORK_ENFORCEMENT.md`

Important requirements:

- Administrator-approved helper installation.
- A dedicated helper account and backend group.
- nftables availability.
- Correct interface configuration.
- Restricted Unix socket permissions.
- Helper authorization for the backend account.
- Explicit enforcement opt-in.
- Verified network topology and device identity.

The example configuration includes machine-specific values such as interface names, UIDs, groups, and filesystem paths. Review and replace them before deployment.

### Enforcement configuration

The application defaults to:

```text
NETRA_NETWORK_ENFORCEMENT_ENABLED=false
NETRA_NETWORK_ENFORCEMENT_DRY_RUN=true
```

Live enforcement must be explicitly enabled and configured.

Do not copy deployment settings blindly onto another host.

---

## API Overview

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Backend health |
| `GET /api/db/health` | Database health |
| `GET /api/devices` | Device inventory |
| `GET /api/dns/analytics/summary` | DNS analytics |
| `GET /api/dns/providers/status` | DNS provider health |
| `GET /api/dns/providers/statistics` | Provider statistics |
| `GET /api/dns/providers/filtering` | Filtering information |
| `POST /api/dns/events/sync` | Synchronize DNS events |
| `GET /api/audits` | Audit records |
| `GET /api/backend/capabilities` | Backend capabilities |
| `GET /api/network/status` | Network and enforcement status |
| `GET /api/network/devices` | Connected network devices |

Per-device network-control routes support plan, apply, verification, state, and history operations.

Sensitive plan/apply operations are restricted to loopback clients.

See `docs/API_REFERENCE.md` for complete endpoint details.

---

## Testing and Validation

Netra includes backend and frontend automated test suites.

### Backend tests

```bash
cd backend

python -m pytest -q
```

**Latest reported result:**

`299 passed`

### Frontend tests

```bash
cd frontend

npm test -- --run
```

**Latest reported result:**

`26 passed`

### Frontend production build

```bash
npm run build
```

**Latest reported result:** Successful TypeScript compilation and Vite production build.

The build reports a bundle-size advisory that can be addressed through future code splitting.

### Network-enforcement tests

The dedicated network-enforcement regression suite includes:

- Device identity validation.
- Authorized and unauthorized helper requests.
- Protocol validation.
- nftables rule generation.
- Device-specific restrictions.
- Restore and rollback behavior.
- Helper availability and failure handling.
- Verification and recovery workflows.

Latest reported dedicated network-enforcement suite result:

`126 passed`

Automated tests and physical network tests are separate forms of validation.

---

## Real-Device Demonstration

Netra was demonstrated on a Debian Linux host using a Wi-Fi hotspot and multiple connected phones.

The recorded test workflow included:

1. Start Netra and open the dashboard.
2. Detect connected devices.
3. Inspect their connection and identity information.
4. Select a device for Internet restriction.
5. Review its dry-run plan.
6. Confirm the operation.
7. Verify that the selected phone loses Internet access.
8. Confirm that another connected phone retains Internet access.
9. Restore the selected phone's Internet access.
10. Verify successful restoration.

The demonstration also exercised the dashboard's enforcement status and helper integration.

The test validates the configured hotspot environment, not arbitrary routers or all possible network topologies.

### Demonstration Videos

Demo recordings are intended to be distributed through the GitLab Release assets rather than stored in the Git repository.

Once the Netra-specific recordings are uploaded, their individual links can be added here.

GitLab repository:

https://code.swecha.org/Meghana_Vanamoju/netra

GitLab releases:

https://code.swecha.org/Meghana_Vanamoju/netra/-/releases

---

## Documentation

Additional technical documentation:

| Document | Description |
|---|---|
| `docs/ARCHITECTURE.md` | Application architecture |
| `docs/API_REFERENCE.md` | Backend API reference |
| `docs/INSTALLATION.md` | Installation and setup |
| `docs/MVP_DEMO_GUIDE.md` | Demonstration workflow |
| `docs/NETWORK_ENFORCEMENT.md` | Firewall enforcement and helper architecture |
| `deploy/README.md` | Privileged helper deployment |

---

## Current Limitations

Netra is designed for controlled local network monitoring and management.

Current limitations include:

- Device-level Internet enforcement requires a supported Linux hotspot and configured nftables path.
- Enforcement behavior on other routers and network topologies requires separate validation.
- DNS client attribution depends on available provider and journal evidence.
- Domain categorization is evidence-based and cannot guarantee detection of every tracker or advertisement.
- Host-local bandwidth measurements are not router-wide accounting.
- Provider configuration snapshots are not complete database backups.
- Machine-specific deployment settings require administrator review.
- Loopback-only access does not replace a full authentication and authorization system.

---

## Roadmap

Future development opportunities include:

- Additional network topology support.
- Improved DNS attribution and privacy intelligence.
- More detailed before-and-after network measurements.
- Additional device identification capabilities.
- Expanded recovery and reconciliation workflows.
- Further dashboard improvements.
- Additional localization and accessibility enhancements.
- More physical-device and network-topology testing.

---

## Contributing

Contributions and improvements are welcome.

Before submitting changes:

1. Review the architecture and safety documentation.
2. Keep network inspection read-only by default.
3. Preserve explicit confirmation for network changes.
4. Do not introduce unrestricted privileged commands.
5. Add or update relevant tests.
6. Run backend tests and frontend validation.
7. Never commit credentials, private network data, databases, or local backups.

---

## License

The repository's licensing terms must be established through an explicit `LICENSE` file before the project is represented as being distributed under a particular open-source license.

---

## Acknowledgements

Netra brings together open-source technologies including Python, FastAPI, React, TypeScript, SQLite, AdGuard Home, Linux nftables, and Docker.

Built with the goal of making home network privacy, monitoring, and device-level access control more transparent and accessible.

**Netra — See your network clearly. Protect it safely.**

## Developer
Vanamoju Lakshmi Meghana