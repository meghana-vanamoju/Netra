# Netra Architecture

```mermaid
graph TD
  Frontend[React Vite] --> Backend[FastAPI]
  Backend --> SQLite[(SQLite)]
  Backend --> Discovery[LAN + router discovery]
  Backend --> Topology[Read-only host hotspot topology]
  Backend --> NetworkControl[Consent-gated per-device control]
  NetworkControl --> Nftables[Owned nftables rules]
  Backend --> ProviderRegistry[DNS provider registry]
  ProviderRegistry --> AdGuard[AdGuard Home HTTP API]
  ProviderRegistry --> PiHole[Pi-hole v6 API]
  Backend --> DNS[DNS ingestion + analytics]
  Backend --> Classifier[Domain classification]
  Backend --> Audit[Privacy audit]
  Backend --> Policy[Policy planner]
  Backend --> Consent[Consent + enforcement]
  Consent --> AdGuard
  Consent --> Snapshots[Config snapshots + rollback]
```

## Live inventory and DNS identity

A successful LAN scan replaces the current process snapshot for its selected
subnet and marks observed persistent rows current. Unobserved rows in the same
subnet remain in SQLite as historical records and are not marked offline by
timeouts or partial scans. The `devices` table is upgraded additively with
`is_current`, `network_subnet`, `last_scan_at`, and `scan_status`; no historical
rows are deleted. MAC address is the preferred stable identifier, while IP
address is used for verified DHCP/DNS association and fallback matching.

AdGuard query-log synchronization persists real provider events. Each event
stores provider provenance, client IP/name, timestamp, category and blocked
status. Ingestion links by exact client IP, then hostname when no IP match exists;
it never invents a domain or device identity. Missing provider configuration,
provider disconnection, and unlinked events are separate UI states.

## LAN Discovery flow

`POST /api/discovery/run` validates the requested private subnet against the
active interface or `NETRA_AUTHORIZED_CIDRS` before launching probes. The
scanner selects at most 64 hosts and submits them to a worker pool capped at
eight threads. Each ICMP subprocess is bounded to 1.25 seconds, and all probe
work shares a 12-second monotonic deadline. Pending work is cancelled when the
deadline expires; observations completed before then are retained and marked
partial.

Before probing, the backend snapshots complete Linux ARP entries. After probing
it reports successful ICMP responders and neighbor entries that appeared or
changed during the scan. An unchanged cached entry alone is not a new
discovery. MAC addresses are retained only from complete neighbor entries;
hostnames are not looked up in API scans, and vendors are never inferred from
MAC prefixes. The route persists observations through the existing inventory
upsert and returns duration, attempted probes, responding hosts, timeout and
error counts, and the partial-result flag. The frontend displays those results
and refreshes both the in-memory scan results and persistent device inventory.

## DNS data flow (Milestone 9.0)

1. `dns/providers/registry.py` selects a provider from environment configuration.
2. `AdGuardHomeAdapter` authenticates with HTTP Basic auth and calls the
   supported `/control/status`, `/control/querylog`, `/control/stats`, and
   `/control/filtering/*` endpoints with bounded timeouts. `PiHoleAdapter`
   preserves compatibility with `NETRA_PIHOLE_URL` / `NETRA_PIHOLE_TOKEN`.
3. `POST /api/dns/events/sync` fetches a bounded, newest-first query log page
   set, normalizes timestamps/domains/clients, and stores rows idempotently via
   `(source, source_event_id)`. Before ingestion, a best-effort dnsmasq journal
   reader may replace only the client IP on copied records when a unique
   forwarded candidate matches domain, query type, gateway/upstream, and the
   configured tolerance. Ambiguous or missing candidates leave provider data
   unchanged, and journal failures never fail the sync.
4. `dns/analytics.py` classifies domains with conservative suffix rules and
   computes totals, unique domains, blocked/allowed counts, category and client
   distributions, top domains, and hourly activity from stored events.
5. Audit findings feed the dry-run planner. Nothing is applied until approval
   with `confirm=true` **and** `NETRA_DNS_ENFORCEMENT_ENABLED=true`. Applied
   user rules are snapshotted so rollback restores the exact prior rule list.

Provider health is derived from real API calls. A running FastAPI process is
never reported as a healthy DNS provider. Secrets stay in environment
variables and are absent from API responses, logs, and status payloads.

Components: frontend dashboard, backend API, SQLite persistence, discovery,
DNS provider adapters, DNS analytics, audit, policy planning, consent-gated
enforcement, snapshots, and recovery.

## Host hotspot client controls

The Connected Devices flow is separate from DNS-provider enforcement. A
read-only topology detector uses the host default route, NetworkManager and
`iw` station data, DHCP leases, and neighbor entries. A device is eligible for
control only when current station evidence is correlated with a private IPv4
address and a fresh, non-conflicting MAC/IP observation. The default-route
signal does not prove that the public Internet is reachable.

Plan requests persist a command projection only. Applying a reviewed plan is
disabled by default and requires explicit environment opt-in, a loopback
request, confirmation, and a fresh device observation. Blocking requires
`NETRA_NETWORK_ENFORCEMENT_DRY_RUN=false`; restoring an existing restriction
is allowed with enforcement enabled even while dry-run is true, as a fail-safe
removal path. The nftables adapter owns a dedicated table/chain and
device-specific set/rule references; it does not flush unrelated tables or
alter Wi-Fi association, router settings, or DNS provider state. The API reads
back the result before reporting access as blocked or allowed.

On hotspot loss or process restart, stored control records are not treated as
proof that a firewall rule is still active. Previously controlled devices
remain visible as disconnected/reconciliation-required, but restoring one
currently requires a fresh hotspot observation. There is no automatic
startup recovery. The implementation has test coverage with fake command
runners, not physical hotspot-client validation; see
[Network enforcement](NETWORK_ENFORCEMENT.md).
