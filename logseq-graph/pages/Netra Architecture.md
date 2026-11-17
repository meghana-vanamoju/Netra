# Netra Architecture

Frontend: React+TS+Vite. Backend: FastAPI. Persistence: SQLite/SQLAlchemy.

Modules: discovery, dns, audit, policy, snapshots, recovery.

Discovery detects the host's default route, optionally reads configured router
leases, and merges them with bounded LAN observations. Router capability is not
inferred from a web port or ARP alone. See [[Router Integration]].
