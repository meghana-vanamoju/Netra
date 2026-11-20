# Privileged helper deployment examples (not executed)

These files are **examples only**. Installing users, creating `/run` and
`/var/lib` directories, editing services, changing capabilities, or starting
units requires explicit administrator approval and was not performed while
implementing this change.

## Files

- `netra-network-helper.service` — restricted helper service. `CAP_NET_ADMIN`
  exists only here, with a minimal bounding set and filesystem hardening. The
  helper creates and owns its own Unix socket; no systemd socket unit is used.
- `netra-backend-helper.conf` — example backend drop-in. The backend remains
  unprivileged and never receives `CAP_NET_ADMIN`.

No `netra-network-helper.socket` unit is provided or supported. The helper
binds its own socket and rejects a pre-existing socket path. Do not install
or activate a systemd socket unit for this helper.

## Exact prerequisites an administrator must approve

1. Create system users/groups `netra-helper` and `netra-backend`, and add the
   backend service account to group `netra-backend`.
2. Create `/run/netra` (mode `0750`, owner `netra-helper:netra-helper`) and
   `/var/lib/netra/network-enforcement` (mode `0700`, owner
   `netra-helper:netra-helper`). The example service also uses systemd
   `RuntimeDirectory=netra` to recreate `/run/netra` on service start.
3. Copy the example service and backend drop-in into `/etc/systemd/system/`,
   replacing `/opt/netra/backend` with the real backend path and replacing the
   machine-specific values below with the real host values:
   - UID `1000` (`NETRA_NETWORK_HELPER_ALLOWED_UIDS`)
   - interface `wlp2s0` (`NETRA_NETWORK_HELPER_ALLOWED_INTERFACE` and
     `NETRA_NETWORK_ENFORCEMENT_INTERFACE`)
   - group names `netra-helper` and `netra-backend`
   - socket path `/run/netra/network-enforcement.sock`
   - state directory `/var/lib/netra/network-enforcement`
4. Verify the backend unit has no `CAP_NET_ADMIN`:
   `systemctl show netra-backend.service -p CapEff`.
5. Review the helper unit's pinned table (`netra`) and interface, then reload
   systemd and start `netra-network-helper.service` directly.
6. Confirm readiness from the API: `GET /api/network/status` must show
   `privilege_model: restricted_local_helper`, `helper_status: available`, and
   `helper_authorized: true`. A `dry_run`/`ready` state must only follow a
   successful helper probe.

## Service-managed socket

The helper creates `/run/netra/network-enforcement.sock` itself under
`umask 077`, then securely resolves group `netra-backend`, sets ownership to
the current helper UID and that GID, and sets mode `0660` before accepting
connections. The backend connects through its membership in `netra-backend`.
The helper independently verifies peer UID/GID with `SO_PEERCRED`.

The parent directory is mode `0750`; only the helper owner and the backend
group can traverse it. Do not chmod the socket `0777`, do not loosen parent
directory permissions, and do not use systemd socket activation.

## Safe restart behavior

Stop and start the helper service rather than deleting its socket manually:

```text
systemctl restart netra-network-helper.service
```

Because the example uses `RuntimeDirectory=netra`, systemd recreates an empty
`/run/netra` on service start. The helper also closes and unlinks only the
socket it created when it stops normally. If the helper crashed and a stale
socket remains, stop the service first, verify that
`/run/netra/network-enforcement.sock` is still owned by
`netra-helper:netra-backend` with mode `0660`, and remove only that socket
path. Do not remove an unknown or foreign socket.

No `sudoers` rule, passwordless sudo, broad root wrapper, or shell entry point
is required or recommended.

## Emergency recovery (manual, administrator-controlled)

If the helper cannot start or a backend crash interrupted an operation:

1. Stop applying new plans. The backend cannot mutate firewall state without
   the helper.
2. Inspect helper state files in `/var/lib/netra/network-enforcement/`. Each
   `device-<id>.json` contains the Netra-owned pre-change snapshot.
3. Use the API `restore` flow for the affected device; the helper removes only
   that device's tagged rules and set element and deletes the saved snapshot.
   If prior Netra-owned rules existed and must be reinstated, use the helper's
   `rollback_restriction` operation, which validates ownership before acting.
4. If the helper is unavailable, an administrator may stop the helper service
   and manually remove only objects named `netra*`/`netra_dev_<id>` in the
   `netra` table. Never flush the whole ruleset, and never touch `filter`,
   `nat`, Docker, NetworkManager, or dnsmasq-owned tables.
5. Re-run read-only verification. Do not claim restoration until read-back
   confirms the expected rules/elements are present or absent.

All helper state writes are atomic, mode `0600`, and checksum-validated. A
corrupt state file is rejected rather than blindly applied.
