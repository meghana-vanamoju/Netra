# Router Integration

- Router support is capability-specific; ARP neighbor evidence is not proof of management access.
- The implemented router-reported inventory adapter is AdGuard Home built-in DHCP, using documented `GET /control/dhcp/status` with backend-only Basic credentials.
- Dynamic and static DHCP leases provide IP, MAC, hostname, and expiry. Vendor, online state, and last seen are unknown unless another source supplies evidence.
- Unsupported routers use the independent bounded LAN neighbor-discovery fallback.
- Router targets and LAN subnets are restricted to the active private LAN or backend `NETRA_AUTHORIZED_CIDRS` entries; LAN probes remain capped at 64 hosts and `/16`.
- Router and LAN observations merge by MAC where available; source provenance and previously seen inventory remain visible.
- Physical evidence: `wlp2s0`, `192.168.88.135/24`, gateway `192.168.88.1`; gateway had a local REACHABLE neighbor entry. Router inventory adapter was not configured, so no management access was claimed.
- See [[Netra Architecture]] and the repository's `docs/ROUTER_COMPATIBILITY.md`.