# Hotspot client internet access controls

Netra's Connected Devices page can optionally block or restore Internet
forwarding for a client connected to an existing Linux Wi-Fi hotspot. This is
an experimental, host-local nftables control. It does not configure or disable
the hotspot, change router/DNS settings, or disconnect the client's Wi-Fi.

## Read-only discovery

The backend uses `ip` and NetworkManager to detect the host default route and
an active Wi-Fi access-point connection. It uses `iw` station data as evidence
that a client is currently associated, then correlates the station MAC with a
DHCP lease or neighbor entry to obtain its IPv4 address. A cached neighbor
entry alone is not treated as an associated client. Missing tools, unreadable
lease files, or incomplete observations are reported as warnings; they do not
authorize a block.

`uplink.connected` currently means that a default route was found. It is not an
external connectivity probe and does not guarantee that the Internet is
reachable.

## Privilege boundary

The FastAPI backend stays unprivileged and never executes `nft`, `iptables`,
`tc`, or `ip` commands that change firewall state. All live Netra firewall
effects go through a dedicated host-local privileged helper. The backend sends
only allowlisted, high-level operations over an AF_UNIX stream socket:
`inspect_state`, `apply_restriction`, `restore_restriction`,
`verify_restriction`, and `rollback_restriction`. It cannot send a shell
command, an nftables string, or an arbitrary table/rule name.

The helper authenticates callers with `SO_PEERCRED` against an explicit UID/GID
allowlist, enforces a bounded JSON schema, pins the permitted Netra table and
hotspot interface in its own configuration, revalidates device identity fields,
and reuses the same Netra-only `NftablesAdapter` as the non-live code path.
`CAP_NET_ADMIN` is intended only for the helper service. See
`deploy/README.md` and the example units in `deploy/` for the exact,
administrator-controlled setup; none of it is installed or activated by Netra.

## Opt in only on a test host

Enforcement is disabled and dry-run by default. After the helper is deployed
and authorized, set:

```text
NETRA_NETWORK_ENFORCEMENT_ENABLED=true
NETRA_NETWORK_ENFORCEMENT_DRY_RUN=false
NETRA_NETWORK_ENFORCEMENT_INTERFACE=wlp2s0
NETRA_NETWORK_ENFORCEMENT_HELPER_SOCKET=/run/netra/network-enforcement.sock
```

The helper separately requires its own pinned settings:

```text
NETRA_NETWORK_HELPER_SOCKET_PATH=/run/netra/network-enforcement.sock
NETRA_NETWORK_HELPER_ALLOWED_UIDS=<backend-uid>
NETRA_NETWORK_HELPER_ALLOWED_TABLE=netra
NETRA_NETWORK_HELPER_ALLOWED_INTERFACE=wlp2s0
NETRA_NETWORK_HELPER_STATE_DIR=/var/lib/netra/network-enforcement
```

Plan generation remains non-mutating. With enforcement enabled,
`restore_internet` remains available while dry-run is true so an existing
Netra-owned restriction can be removed; blocking requires dry-run to be false.
Setting enforcement to false disables both operations. Changing configuration
requires restarting the affected process. A missing helper, denied peer
credentials, timeout, or rejected request is reported as unavailable; it is
never reported as a successful apply.

Readiness is helper-aware. `GET /api/network/status` reports
`privilege_model: restricted_local_helper`, `helper_status`,
`helper_authorized`, `helper_socket_path`, the backend's informational
`backend_cap_net_admin`, and helper-based `nftables_inspection_status`. The
backend's own `CapEff` is informational only and is no longer an apply gate.
The helper's `inspect_state` operation performs a read-only nftables
inspection; no write permission is probed. Kernel policy can still reject a
later mutation, so only read-back verification counts as success.

The forward chain drops IPv4 packets using the selected client's address set
and drops IPv6 packets using the client's observed Ethernet MAC on the hotspot
ingress/egress path. This prevents privacy IPv6 source addresses from evading
the source-side drop, but is still subject to the actual host packet path and
must be tested with IPv6 enabled on a test client. `physical_connectivity_status`
remains `not_tested`; rule verification is not a phone reachability test.

Plan and apply routes accept loopback peer addresses only. Apply also requires
`confirm: true`, an approver value, and a persisted plan matching the device and
action. Review the affected device, interface, IP, MAC, warnings, and commands
before confirmation. Loopback-only access is not authentication; do not expose
the backend through a remotely accessible reverse proxy.

## Scope and recovery behavior

- Each client has a separate nftables set, and its rule is scoped to the
  hotspot interface and MAC address. Netra does not flush foreign nftables
  tables or chains.
- IP changes are not automatically transferred to another client. A changed
  or conflicting identity requires reconciliation.
- A disconnected device remains visible with `reconciliation_required` when
  there is a saved applied control. It cannot be restored through the normal
  UI until the client is freshly observed on the hotspot.
- Netra does not automatically reapply or restore controls after backend or
  host restart. Persisted state is not treated as proof that a rule remains
  active; use Verify against the live nftables state.
- Before a mutation, the helper atomically saves a checksum-validated,
  Netra-owned pre-change snapshot per device under its protected state
  directory. A backend crash or helper restart does not lose that snapshot.
  `restore_restriction` is idempotent for the selected device;
  `rollback_restriction` restores a prior Netra-owned state when one existed.
- Mutation requests are serialized inside the helper to prevent concurrent
  apply/restore races for the same or different devices. Requests that name a
  different table, interface, subnet, IP, or MAC are rejected before any
  adapter is invoked.
- `allowed` and `blocked` are displayed only when live verification succeeds.
  A missing hotspot, unavailable `nft`, identity conflict, or unreadable
  enforcement state is reported as unknown or an error, not success.
- The control governs forwarding from this host. It does not stop local
  communication on the hotspot, control VPN or encrypted-DNS behavior outside
  this forwarding path, or provide router-wide protection.

## Host-local emergency recovery

This procedure does not require Netra, the hotspot, or the client to be
available. Use a local administrator shell on the Netra host. Substitute the
configured table name if it is not `netra`.

If the helper is running, first stop new applies and use the API restore/verify
flow for the affected device. The helper's saved snapshot is listed in
`inspect_state` as `recoverable_devices`; `rollback_restriction` uses it only
after revalidating the target and ownership. If the helper is unavailable,
inspect `/var/lib/netra/network-enforcement/device-<id>.json` from a local
administrator shell and use the manual steps below as the fallback.

First inspect the table and handles without changing state:

```text
sudo nft -a list table inet netra
```

If the table is dedicated to Netra and its `netra-managed` ownership comment
and contents are confirmed, remove only that table:

```text
sudo nft delete table inet netra
```

If the table contains any non-Netra objects, do not delete the table. Identify
only rules with the expected `netra-device-<id>-egress` and
`netra-device-<id>-ingress` comments, then delete those exact handles from
`netra_forward`:

```text
sudo nft delete rule inet netra netra_forward handle <HANDLE>
```

Do not use `flush ruleset`, flush another table, or guess handles. Removing
the tagged drop rules removes Netra's blocking effect; a leftover per-device
set element alone does not drop packets. Re-list the table and confirm the
selected device's tagged rules are absent. If the table name, ownership, or
rule scope is uncertain, stop and have a Linux firewall administrator review
the read-only listing before deleting anything.

## Validation status

Backend tests use fake command runners and in-memory nftables/helper doubles.
They cover discovery parsing, identity validation, per-device rule ownership,
IPv4/IPv6 rule construction, dry-run planning, apply gating, verification,
helper peer authentication, malformed/arbitrary-command rejection, helper
unavailability/permission/timeout, partial apply/restore rollback, concurrency,
and restart recovery. Latest run: `python3 -m pytest -q` in `backend/` reported
**298 passed, 1 failed**; the single failure is the pre-existing
`test_dns_integration_milestone9.py::test_provider_sync_is_idempotent_and_failure_recovers`
and is unrelated to network enforcement (it was present before this change).
Targeted network tests: 126 passed. Frontend `npm test` reported **26 passed**,
and `npm run build` succeeded.

The helper manages its own Unix socket. Do not install or activate a systemd
socket unit for it; start `netra-network-helper.service` directly. The helper
creates the socket under `umask 077`, resolves group `netra-backend`, sets
ownership to the helper UID and that GID, and sets mode `0660` before accepting
connections.

No live nftables command, NetworkManager change, or physical hotspot client
test is part of the automated suite. Validate on a disposable test host with
at least two client devices before considering deployment; confirm that only
the selected client's forwarding changes and that restoration works before
relying on the feature.
