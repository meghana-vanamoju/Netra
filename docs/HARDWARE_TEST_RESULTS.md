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
