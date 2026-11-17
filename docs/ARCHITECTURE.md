# Netra Architecture

```mermaid
graph TD
  Frontend[React Vite] --> Backend[FastAPI]
  Backend --> SQLite[(SQLite)]
  Backend --> Discovery
  Backend --> DNS
  Backend --> Audit
  Backend --> Policy
```

Components: frontend dashboard, backend API, SQLite persistence, discovery, DNS analytics, audit, policy planning, snapshots, recovery.
```
/home/meghana/Documents/viswam/Netra/docs/INSTALLATION.md