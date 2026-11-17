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

- `GET http://127.0.0.1:8000/api/discovery/network` returned HTTP 200 and the
  interface/address/gateway/subnet above.
- The existing neighbor table showed `192.168.88.1` in `REACHABLE` state.
- `POST /api/router/test?ip=192.168.88.1` returned HTTP 200 with
  `network_reachable: true` and `management_interface_available: false`. This
  is neighbor-table evidence only, not a router management test.
- `POST /api/router/devices?ip=192.168.88.1` returned HTTP 200 with
  `status: unsupported` and an empty device list. No AdGuard Home adapter was
  configured for this exact gateway IP.
- IPv4 loopback health returned HTTP 200. IPv6 loopback to port 8000 failed;
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
through a Vite proxy whose `'/health'` target is `http://127.0.0.1:8000`
(i.e. this backend). Stale Firefox history also contains direct visits to
`http://127.0.0.1:8000/health` and `http://localhost:8000/health`. No Netra
code was changed for these 404s and the external project was not modified.

### Origin-related failure reproduced

Opening the Vite frontend at `http://[::1]:5173` — the IPv6 loopback address
the dev server actually binds to on this host — reproduced a complete failure:
every API call was blocked at the CORS layer, the page showed `API unavailable`
and `Could not connect to http://127.0.0.1:8000…` messages, and **no LAN
discovery POST reached FastAPI**. The backend CORS allowlist now also accepts
`http://[::1]:5173`; the required `http://localhost:5173` and
`http://127.0.0.1:5173` origins were and remain allowed. Discovery buttons
stay disabled while the active network is still being detected, so an early
click cannot produce an empty-submit with no POST.
