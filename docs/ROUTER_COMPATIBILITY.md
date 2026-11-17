# Router Compatibility

Netra does not claim universal router-management support. Router vendors expose
different authenticated APIs, and an open web port or an ARP entry does not
prove that a device inventory API exists.

| Product/interface | Device inventory | Authentication | Evidence/status |
|---|---|---|---|
| AdGuard Home built-in DHCP | DHCP leases and configured static leases from `/control/dhcp/status` | HTTP Basic; backend-only environment configuration | Implemented against AdGuard Home's published OpenAPI schema. Requires exact-IP URL configuration. |
| Generic router with no configured adapter | Not available through router API | Unknown | Reported as unsupported; LAN fallback remains available. |
| Other router vendors | Not implemented | Not assessed | No undocumented endpoints or protocol assumptions. |

AdGuard Home support requires:

```text
NETRA_ADGUARD_API_URL=http(s)://<router-ip>:<web-port>
NETRA_ADGUARD_USERNAME=<AdGuard Home username>
NETRA_ADGUARD_PASSWORD=<secret>
```

Router IPs must be on the active private LAN or in a backend-configured
`NETRA_AUTHORIZED_CIDRS` comma-separated allowlist. LAN discovery has the same
scope check and accepts only subnets contained in an authorized range; each
scan is capped at `/16`.

The URL hostname must match the router IP submitted in Netra. AdGuard Home's
DHCP status endpoint exposes the built-in server's current configuration,
dynamic leases, and static leases. It does not expose a general client list for
leases managed by another DHCP server. The published lease fields include MAC,
IP, hostname, and expiration; online state, vendor, and last seen are not
provided and remain unknown.

Netra only issues a GET to this endpoint. It never writes router configuration,
changes DNS or firewall settings, blocks devices, or reboots the router. AdGuard
Home may not provide a read-only role for its API credentials, so the configured
account can have broader privileges than Netra uses. Authentication failures
are reported without returning credential material.

LAN discovery is independent of router compatibility. Its coverage depends on
the Netra host's local neighbor table, bounded ICMP probes, subnet selection,
network permissions, and Wi-Fi isolation. A zero result is not proof that the
network contains no devices.