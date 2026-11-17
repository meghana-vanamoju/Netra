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