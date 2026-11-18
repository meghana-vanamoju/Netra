# Hardware Test Results

## Workplace Wi-Fi Read-Only Check

**Date:** 2026-11-17 (system date; API responses observed around 09:25 UTC)

The current network was detected at test time rather than inferred from the
supplied prior values:

| Field | Observed value |
|---|---|
| Interface | `wlp2s0` |
| Laptop IPv4 | `192.168.88.135` |
| Gateway | `192.168.88.1` |
| Subnet | `192.168.88.0/24` |
| Interface route | `192.168.88.0/24 dev wlp2s0` |

Read-only results:

- `GET http://127.0.0.1:8084/api/discovery/network` returned HTTP 200 and the
  interface/address/gateway/subnet above.
- The existing neighbor table showed `192.168.88.1` in `REACHABLE` state.
- `POST /api/router/test?ip=192.168.88.1` returned HTTP 200 with
  `network_reachable: true` and `management_interface_available: false`. This
  is neighbor-table evidence only, not a router management test.
- `POST /api/router/devices?ip=192.168.88.1` returned HTTP 200 with
  `status: unsupported` and an empty device list. No AdGuard Home adapter was
  configured for this exact gateway IP.
- IPv4 loopback health returned HTTP 200. IPv6 loopback to port 8084 failed;
  the backend listener is on `127.0.0.1`, which confirmed the frontend's
  previous `localhost` default could resolve to an unavailable `::1` listener.

No router credentials were supplied. No router management interface request,
active router port probe, or LAN host scan was performed. The physical test
therefore verifies local network detection and passive gateway presence only;
it does not establish router inventory compatibility. Automated lease and
error-path tests use mocked responses and are not physical router tests.

The neighbor table also contained a mixture of `STALE` and `FAILED` entries.
That state is a transient local cache, not a complete or authoritative device
inventory. No vendor inference was made from MAC prefixes.

## Office Wi-Fi LAN Discovery Verification (browser-triggered)

**Date:** 2026-11-17. This section records the post-integration verification on
the office Wi-Fi, after the subnet query-encoding fix. It supersedes the
passive-only scope of the section above; the router-management caveat below
still applies.

| Field | Verified value |
|---|---|
| Subnet | `192.168.88.0/24` |
| Gateway | `192.168.88.1` |
| Browser request | `POST /api/discovery/run?subnet=192.168.88.0%2F24` from Firefox (`Origin: http://localhost:5173` and `Origin: http://127.0.0.1:5173`) |
| HTTP response | **200** with `{"discovered": 50, "subnet": "192.168.88.0/24"}` |
| Devices inventory | **51 records** after the scan, with IP, MAC, classification, and source visible |
| Example source | `lan-discovery,arp` (also displayed as `lan-discovery.arp`) |

### Why 50 discovered hosts and 51 inventory records

The counts describe different sets and are not expected to match:

- The scan reported **50 hosts on `192.168.88.0/24`**, including the gateway
  `192.168.88.1`. The gateway is not an additional inventory record.
- The inventory endpoint returned **51 records**. Fifty are the current
  `192.168.88.x` scan results. The remaining record is a pre-existing
  `10.252.213.78` gateway entry (`_gateway`, source `lan-discovery`,
  `first_seen` 2026-11-17T06:51:06Z) from an earlier scan in a different
  network context.
- Inventory writes are upserts keyed by MAC/IP. They refresh or add devices
  seen in the submitted subnet; they do not delete records belonging to other
  subnets. Records are deduplicated, so repeated scans do not create extra
  rows. No count adjustment or forced reconciliation was performed.

### Discovery limitations

- Discovery is ARP/neighbor-table based. It reports addresses present in the
  local neighbor cache plus active probe results; it cannot guarantee a
  complete, stable inventory of every device on the Wi-Fi.
- Neighbor entries may be `STALE` or `FAILED`, and a device that is asleep,
  isolated, or outside the scanned subnet may be missing. Vendor names are not
  inferred from MAC prefixes, and `hostname` may be null.
- Results are a point-in-time observation from the backend host, not a
  continuous monitoring stream. Private-LAN-only validation remains enabled:
  public, loopback, link-local, multicast, and malformed CIDRs are rejected.

### Router management capability remains unverified

The successful LAN scan does **not** verify router management support:

- No router credentials or management API were supplied or used.
- `POST /api/router/devices?ip=192.168.88.1` still reports `status:
  unsupported` with an empty list; no AdGuard Home adapter is configured for
  that exact gateway IP.
- `POST /api/router/test?ip=192.168.88.1` confirms neighbor-table reachability
  only, not an authenticated management session, DHCP lease access, policy
  application, or DNS enforcement.
- No router configuration was changed, and no enforcement, verification, or
  snapshot rollback capability is claimed.

## Personal Wi-Fi LAN Discovery Verification (browser-triggered)

**Date:** 2026-11-17. This section is separate from the office Wi-Fi results
above and records the first browser-triggered scan on the user's personal
router at `192.168.29.0/24`.

| Field | Observed value |
|---|---|
| Interface | `wlp2s0` |
| Laptop IPv4 | `192.168.29.4/24` |
| Gateway | `192.168.29.1` (MAC `84:90:0A:FA:5D:30`) |
| Subnet | `192.168.29.0/24` |
| Gateway ping | 4/4 replies, 0% loss (about 3–5 ms across checks) |
| Backend health | `GET /api/health` → HTTP 200 |
| Router capability | `GET /api/router/capabilities?ip=192.168.29.1` → HTTP 200, `network_reachable: true`, `management_interface_available: false`, `connected_devices: unsupported`, `dhcp_leases: unsupported`, `dns_logs: unsupported`, `authentication_required: unknown` |
| Browser | Headless Chrome driven over CDP at `http://localhost:5173/#discovery`, clicking **Detect router** and then **LAN discovery** |
| Browser request | `POST /api/discovery/run?subnet=192.168.29.0%2F24` — HTTP **200** |
| Discovery response | `{"discovered": 2, "subnet": "192.168.29.0/24"}` |
| UI result | `LAN endpoint returned 2 observation(s) from 192.168.29.0/24.` |
| Unified inventory | **54 records** after the scan, including `192.168.29.1` (`_gateway`, source `arp`) and `192.168.29.30` (source `arp`) |
| JS errors | None; no failed Netra API response during the workflow |

The inventory retained the earlier `192.168.88.x` and `10.252.213.78`
records. This confirms that the personal-subnet scan added/refreshed devices
without silently deleting records from other subnets. Only two hosts were
returned because LAN discovery reports the point-in-time ARP/neighbor table
plus bounded probes on the backend host; it is not a claim that the router has
only two connected devices. Sleeping, isolated, or not-yet-observed clients can
be absent, and no vendor inference was made from MAC prefixes. The 64-host
probe limit was unchanged. Router management APIs, authenticated sessions,
DHCP lease access, policy application, and DNS enforcement remain unverified
and are reported as `unsupported` by the backend. No router configuration or
DNS setting was modified.

### Repeated bare `/health` 404s are external

The repeated `GET /health` 404 lines in the backend terminal are not produced
by Netra. Netra only calls `/api/health`; no Netra source references a bare
`/health` path. The requests come from the separate Prism AI Code Reviewer
frontend, whose `frontend/src/services/api.ts` calls `request<HealthResponse>('/health')`
through a Vite proxy whose `'/health'` target is `http://127.0.0.1:8084`
(i.e. this backend). Stale Firefox history also contains direct visits to
`http://127.0.0.1:8084/health` and `http://localhost:8084/health`. No Netra
code was changed for these 404s and the external project was not modified.

### Origin-related failure reproduced

Opening the Vite frontend at `http://[::1]:5173` — the IPv6 loopback address
the dev server actually binds to on this host — reproduced a complete failure:
every API call was blocked at the CORS layer, the page showed `API unavailable`
and `Could not connect to http://127.0.0.1:8084…` messages, and **no LAN
discovery POST reached FastAPI**. The backend CORS allowlist now also accepts
`http://[::1]:5173`; the required `http://localhost:5173` and
`http://127.0.0.1:5173` origins were and remain allowed. Discovery buttons
stay disabled while the active network is still being detected, so an early
click cannot produce an empty-submit with no POST.

## Bounded Concurrent Discovery Benchmark

**Date:** 2026-11-18. The live scan used the same office subnet as the previous
browser-triggered verification: `192.168.88.0/24`. The legacy timing and
50-observation count below are the previously reported Netra measurements;
responder and timeout counts were not captured during that run. New values are
from an actual HTTP request to the running backend, not a mocked test.

| Metric | Previous sequential implementation | Bounded concurrent implementation |
|---|---:|---:|
| Total duration | 59–63 seconds (reported) | 6.033 seconds backend |
| Probe limit / attempted | 64 maximum; 64 were attempted | 64 attempted |
| Hosts responding to ICMP | Not recorded | 25 |
| No-reply / timeout count | Not recorded | 39 |
| Discovery observations | 50 reported by the prior browser run | 25 |
| IP/MAC evidence | Per-host evidence was not recorded with the legacy aggregate | 25/25 had an IP and a complete neighbor-table MAC |
| Hostname/vendor | Legacy flow attempted reverse DNS; per-host outcome not recorded | 0 hostnames; vendors remain Unknown |
| Probe errors / partial status | Not recorded | 0 errors; `partial_results: true` because hosts timed out |
| Persisted inventory / UI | 51 records in the prior report | API returned 61 persistent records; UI displayed 51 merged rows |

The new live run was approximately **9.8–10.4x faster** than the reported
59–63-second baseline. Its 25 records are supported by successful ICMP replies
and current complete neighbor-table entries; no hostname or vendor was
fabricated. The old run's 50-record aggregate did not preserve responder
counts or a per-IP evidence snapshot, so the 25-record difference cannot be
classified conclusively as false positives. The old implementation included
unchanged cached ARP entries, which the new implementation deliberately
excludes unless the host replies or its neighbor entry changes during the scan.

This measurement was triggered from the browser at `http://localhost:5173`.
The API returned 25 current observations, all 25 with MAC evidence and no
hostnames. The UI also displayed retained inventory records; these are not
counted as current scan discoveries. The 61-record API inventory and 51-row
UI merge are separate views, and no existing inventory rows were deleted.

The exact new result was `discovered: 25`, `probes_attempted: 64`,
`hosts_responding: 25`, `timeout_count: 39`, `probe_errors: 0`, and
`partial_results: true`. This is a point-in-time office-network observation;
Wi-Fi isolation, firewalls, sleeping clients, and ICMP filtering can affect
both responder and neighbor-table evidence. Automated concurrency, timeout,
authorization, stale-entry, and API error tests use deterministic mocks and
are not part of these live measurements. No router or DNS configuration was
changed.

## Real AdGuard Home DNS Monitoring (Milestone 9.0)

**Date:** 2026-11-17. The existing lab container `netra-adguardhome-1`
(`adguard/adguardhome:v0.107.50`) was started with
`docker compose -f docker-compose.adguard.yml up -d`; no duplicate instance was
created. The lab password was reset locally because only a bcrypt hash was
available; the plaintext is kept in the backend environment outside Git.

### Connectivity and real query retrieval

| Check | Result |
|---|---|
| `GET /control/status` with configured credentials | HTTP **200**, version **v0.107.50**, `protection_enabled: true` |
| Backend `GET /api/dns/providers/status` | `state: healthy`, `authentication: configured`, `version: v0.107.50`, `query_log/statistics/filtering: available`, capabilities include API connectivity/authentication/protection/query log/statistics/filtering |
| Controlled queries | `dig @127.0.0.1 -p 53 <domain> A` for advertising, analytics, telemetry, CDN, social, essential, and unknown suffixes; query log confirmed each event |
| `POST /api/dns/events/sync` (first run) | `fetched: 19`, `inserted: 19`, `duplicates: 0`, `skipped: 0` |
| Repeated sync while healthy | `inserted: 0`, no duplicate rows; stored total unchanged |
| Analytics from real events | `total: 19`, `unique_domains: 19`, `blocked: 9`, `allowed: 10`, `blocking_percentage: 47.37` |
| Category distribution | Tracking/Analytics 6, Advertising 3, Unknown 2, Essential services 2, Social media 2, Content delivery 2, Telemetry 2 |
| Evidence fields retained | client `172.22.0.1`, provider reasons (`FilteredBlackList`, `NotFilteredNotFound`), query type `A`, upstream, hourly timeline, category evidence |
| Source label | All 19 rows have `source: adguard-home`; no synthetic event was used for these counts |

### Provider interruption and recovery

```text
docker compose -f docker-compose.adguard.yml stop
GET /api/dns/providers/status -> state: unreachable (HTTP 200 report)
POST /api/dns/events/sync      -> HTTP 503, state: unreachable

docker compose -f docker-compose.adguard.yml start
GET /api/dns/providers/status -> state: healthy, version v0.107.50
POST /api/dns/events/sync      -> HTTP 200, fetched 19, duplicates 19, inserted 0
```

The container is running again. No stored event was deleted during the outage
or recovery.

### Consent, enforcement, verification, rollback

A lab client device (`172.22.0.1`) was registered and seven new controlled
queries were generated and synced. Audit `id=1` produced a tracking/telemetry
finding; policy `id=1` and dry-run `id=1` identified seven target domains
(`m9e-ads.doubleclick.net`, `m9e-track1..6.google-analytics.com`) and explicitly
excluded the essential-service domain.

1. `POST /api/policies/1/approve?plan_id=1&confirm=true` → HTTP 200.
2. `POST /api/policies/1/apply` → HTTP 200, `status: applied`,
   `provider: adguard`, seven domains, `snapshot_id: 2`, approver `local-user`.
3. AdGuard `/control/filtering/status` showed exactly the seven expected user
   rules — this is direct provider evidence, not an API success claim.
4. Each controlled domain was queried with `dig` through the lab listener.
   AdGuard's query log showed `FilteredBlackList` for all seven; sync inserted
   nine new real records.
5. `GET /api/verification/policy/1` → `status: verified` with seven evidence
   entries containing domain, reason, and observation timestamp.
6. `POST /api/snapshots/2/rollback?confirm=true` → `status: restored`, rules 0.
   AdGuard user rules were empty afterward; policy status became `reverted`
   and the execution record became `rolled_back`.

An earlier apply attempt returned `malformed_response` because AdGuard's
`set_rules` success response has an empty body; the adapter was fixed to treat
an empty 2xx body as success, its one partially added rule was restored from
snapshot `id=1`, and the final flow above was run cleanly. This failure path is
now covered by an automated test.

**Capability boundary:** default AdGuard filter lists also block the selected
advertising/analytics suffixes, so filtered responses alone do not prove that
the Netra-added rule caused the block. Causality here rests on the exact rule
list observed in AdGuard plus rollback restoring that list. No personal router
DNS setting, upstream resolver, or system-wide traffic route was changed.

### Reproduce

```bash
docker compose -f docker-compose.adguard.yml up -d
cd backend && python3 -m uvicorn main:app --port 8001
# with NETRA_ADGUARD_* and NETRA_DNS_ENFORCEMENT_ENABLED in the environment
dig @127.0.0.1 -p 53 m9-check.google-analytics.com A +short
curl -s -X POST http://127.0.0.1:8001/api/dns/events/sync
curl -s http://127.0.0.1:8001/api/dns/analytics/summary
curl -s http://127.0.0.1:8001/api/dns/providers/status
```
