# Router Integration Architecture

## Workflow

The LAN Discovery page asks the backend to detect its active IPv4 interface,
address, default gateway, and subnet through `GET /api/discovery/network`. This
uses the local routing table and interface address data; it does not contact
the router. The user can edit the gateway and private subnet before starting
discovery.

`POST /api/router/test?ip=...` checks the local ARP table for the requested
private IPv4 address. A positive result means only that the host has a neighbor
entry. It is not evidence of router management access. Generic TCP port 80
checks are intentionally not treated as router capability detection.

`GET /api/router/capabilities?ip=...` reports only implemented/configured
capabilities. `POST /api/router/devices?ip=...` retrieves connected-device
information only when an explicitly configured adapter matches that exact IP.
The combined UI action retrieves supported router data, runs bounded LAN
discovery on the selected private subnet, then refreshes the unified inventory.
Router management is optional; LAN discovery works without it.

## Supported Adapter

The only router-reported inventory adapter currently implemented is AdGuard
Home's documented read-only `GET /control/dhcp/status` endpoint. The adapter
reads the `leases` and `static_leases` arrays and maps IP, MAC, hostname,
expiration, and lease type. The upstream API does not provide per-lease online
state, vendor, or last-seen values, so Netra reports those as unknown. This is
AdGuard Home's built-in DHCP server inventory; it does not retrieve leases from
an unrelated router's DHCP server.

The adapter is enabled only when `NETRA_ADGUARD_API_URL` is set and its
hostname exactly matches the entered router IP. Configure `NETRA_ADGUARD_USERNAME`
and `NETRA_ADGUARD_PASSWORD` on the backend host when authentication is
required. AdGuard Home uses HTTP Basic authentication. Keep these environment
variables out of source control and process logs. Credentials are not accepted
from the browser, returned by APIs, or included in error text. TLS should be
used when the AdGuard Home endpoint is exposed beyond a trusted local segment.

No generic router endpoint, authentication bypass, or other vendor protocol is
assumed. Unsupported, unauthenticated, denied, timed-out, empty, and successful
responses are distinct.

## LAN Fallback and Inventory

LAN discovery reads the host's ARP neighbor table, sends at most 64 sequential
ICMP probes inside the explicitly selected private IPv4 subnet, then reads the
neighbor table again. It does not scan outside that subnet. Probes may not
populate neighbors when ICMP is blocked, and Wi-Fi client isolation, container
networking, host permissions, or platform differences can limit visibility.
The current interface-detection implementation uses Linux `ip -j route` and
`ip -j addr`; unsupported platforms return unknown network details and allow
manual values.

Router and LAN observations merge by normalized MAC address. IP is a fallback
only when one observation lacks a MAC or when matching a stored record with no
MAC; conflicting MAC addresses are not collapsed. A new IP for a known MAC
updates that device, while null observations do not erase stored hostname or
vendor data. First-seen is retained, last-seen updates on successful
observations, and source/lease metadata is stored with the device. The current
discovery results endpoint represents the latest LAN run plus the most recent
router retrieval; older inventory records remain visible as previously seen.

## API Contract

| Method and path | Behavior |
|---|---|
| `GET /api/discovery/network` | Active interface, IPv4 address, gateway, and subnet, nullable when unavailable. |
| `POST /api/router/test?ip={ipv4}` | Local neighbor presence; does not assert management support. |
| `GET /api/router/capabilities?ip={ipv4}` | Implemented capability report and whether the exact-IP AdGuard adapter is configured. |
| `POST /api/router/devices?ip={ipv4}` | Adapter status, auth status, and device list; successful results update inventory. |
| `POST /api/discovery/run?subnet={cidr}` | Bounded local discovery and inventory update. |
| `GET /api/discovery/results` | Latest LAN observations merged with the most recent router records. |
| `GET /api/devices?limit=200` | Persistent unified device inventory. |

Router targets and LAN subnets must belong to the detected active private
subnet or a backend-configured, comma-separated `NETRA_AUTHORIZED_CIDRS`
allowlist. Router targets must be IPv4; LAN scans must be private IPv4 networks
no wider than `/16` and contained in an authorized range. Browser requests use
the shared API client and the backend allows the local Vite origins
`localhost:5173` and `127.0.0.1:5173`.

## Evidence

Automated adapter tests use mocked responses. The workplace network's live
interface, address, gateway, and route are recorded in
[HARDWARE_TEST_RESULTS.md](HARDWARE_TEST_RESULTS.md). No router management
request or LAN probe was made during that evidence collection.