#!/usr/bin/env python3
"""Restricted, host-local firewall helper for Netra.

This process is the only component intended to hold ``CAP_NET_ADMIN``. It
accepts a small, allowlisted operation set over a local Unix-domain socket,
checks the caller's OS credentials, revalidates every target, and delegates to
the existing Netra-only nftables adapter. It never accepts command strings.

This module is inert unless ``main()`` is called by the deployed service.
"""

import grp
import hashlib
import json
import os
import socket
import socketserver
import stat
import struct
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from network_enforcement.config import NetworkEnforcementConfig
from network_enforcement.errors import (
    HelperError,
    HelperPermissionError,
    HelperProtocolError,
    NetworkEnforcementError,
)
from network_enforcement.nftables import NftablesAdapter
from network_enforcement.privileged_protocol import (
    PROTOCOL_VERSION,
    encode_message,
    normalize_socket_path,
    read_message,
    validate_request,
)
from network_enforcement.target import DeviceTarget

DEFAULT_STATE_DIR = "/var/lib/netra/network-enforcement"
HELPER_SOCKET_GROUP = "netra-backend"
HELPER_SOCKET_MODE = 0o660


def _parse_ids(raw):
    values = set()
    for part in str(raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdecimal():
            raise ValueError("helper IDs must be decimal integers")
        values.add(int(part))
    return frozenset(values)


def _validate_directory(path):
    normalized = normalize_socket_path(str(path))
    info = os.stat(normalized)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("helper state path is not a directory")
    if info.st_mode & stat.S_IWOTH:
        raise ValueError("helper state directory must not be world-writable")
    return normalized


def _resolve_socket_group():
    """Resolve the one group allowed to connect to the helper socket."""
    try:
        return grp.getgrnam(HELPER_SOCKET_GROUP).gr_gid
    except (KeyError, OSError) as exc:
        raise HelperPermissionError(
            "The helper socket group could not be resolved",
            code="helper_socket_group_unavailable",
            details={"group": HELPER_SOCKET_GROUP},
        ) from exc


def _path_identity(name, *, dir_fd=None):
    info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    return info.st_dev, info.st_ino


@dataclass(frozen=True)
class HelperConfig:
    socket_path: str
    allowed_uids: frozenset[int]
    allowed_gids: frozenset[int]
    allowed_table: str
    allowed_interface: str | None
    command_timeout_seconds: float
    state_dir: str | None

    @classmethod
    def from_env(cls, environ=None):
        env = environ if environ is not None else os.environ
        state_dir = env.get("NETRA_NETWORK_HELPER_STATE_DIR") or None
        if state_dir is not None:
            state_dir = _validate_directory(state_dir)
        return cls(
            socket_path=normalize_socket_path(
                env.get("NETRA_NETWORK_HELPER_SOCKET_PATH")
                or "/run/netra/network-enforcement.sock"
            ),
            allowed_uids=_parse_ids(env.get("NETRA_NETWORK_HELPER_ALLOWED_UIDS")),
            allowed_gids=_parse_ids(env.get("NETRA_NETWORK_HELPER_ALLOWED_GIDS")),
            allowed_table=env.get("NETRA_NETWORK_HELPER_ALLOWED_TABLE") or "netra",
            allowed_interface=env.get("NETRA_NETWORK_HELPER_ALLOWED_INTERFACE") or None,
            command_timeout_seconds=float(
                env.get("NETRA_NETWORK_HELPER_COMMAND_TIMEOUT_SECONDS") or "3.0"
            ),
            state_dir=state_dir,
        )


class SnapshotStore:
    """Protected, per-device pre-change snapshots for crash recovery."""

    def __init__(self, directory):
        self.directory = _validate_directory(directory) if directory else None

    def _path(self, device_id):
        if isinstance(device_id, bool) or not isinstance(device_id, int) or device_id <= 0:
            raise HelperProtocolError(
                "Invalid snapshot device id", code="helper_invalid_device"
            )
        return os.path.join(self.directory, f"device-{device_id}.json")

    @staticmethod
    def _checksum(state):
        raw = json.dumps(state, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def save(self, device_id, state):
        if self.directory is None:
            return
        record = {
            "device_id": device_id,
            "checksum": self._checksum(state),
            "state": state,
        }
        path = self._path(device_id)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".netra-snapshot-", dir=self.directory
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(record, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load(self, device_id):
        if self.directory is None:
            return None
        path = self._path(device_id)
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise HelperError(
                "Saved enforcement state could not be read",
                code="helper_state_unreadable",
                details={"error": str(exc)},
            ) from exc
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HelperError(
                "Saved enforcement state is invalid",
                code="helper_state_invalid",
            ) from exc
        if (
            not isinstance(record, dict)
            or record.get("device_id") != device_id
            or not isinstance(record.get("state"), dict)
        ):
            raise HelperError(
                "Saved enforcement state has an unexpected shape",
                code="helper_state_invalid",
            )
        state = record["state"]
        if record.get("checksum") != self._checksum(state):
            raise HelperError(
                "Saved enforcement state failed its integrity check",
                code="helper_state_integrity_failed",
            )
        return state

    def delete(self, device_id):
        if self.directory is None:
            return
        try:
            os.unlink(self._path(device_id))
        except FileNotFoundError:
            pass

    def recoverable_devices(self):
        if self.directory is None:
            return []
        devices = []
        for path in Path(self.directory).glob("device-*.json"):
            suffix = path.name.removeprefix("device-").removesuffix(".json")
            if suffix.isdecimal() and int(suffix) > 0:
                devices.append(int(suffix))
        return sorted(devices)


class HelperService:
    """Operation dispatcher. All firewall effects happen through its adapter."""

    def __init__(self, config: HelperConfig, *, adapter_factory=None, store=None):
        self.config = config
        self.store = store if store is not None else SnapshotStore(config.state_dir)
        self._adapter_factory = adapter_factory or self._default_adapter
        self._lock = threading.Lock()

    def _default_adapter(self, table, interface):
        nft_config = NetworkEnforcementConfig(
            enabled=True,
            dry_run=False,
            table=table,
            interface=interface,
            ifb=None,
            command_timeout_seconds=self.config.command_timeout_seconds,
            observation_ttl_seconds=300,
        )
        return NftablesAdapter(nft_config)

    def _adapter_for(self, request):
        interface = self.config.allowed_interface
        if interface is None:
            target = request.get("target") or {}
            interface = target.get("interface")
        if not interface:
            raise HelperError(
                "The helper has no pinned enforcement interface",
                code="helper_interface_not_configured",
            )
        return self._adapter_factory(request["table"], interface)

    def authenticate(self, peer_credentials):
        """Require an explicitly allowed OS uid or gid."""
        try:
            _pid, uid, gid = struct.unpack("3i", peer_credentials)
        except (TypeError, ValueError, struct.error) as exc:
            raise HelperPermissionError(
                "Caller credentials could not be read",
                code="helper_credentials_unavailable",
            ) from exc
        if uid in self.config.allowed_uids or gid in self.config.allowed_gids:
            return {"uid": uid, "gid": gid}
        raise HelperPermissionError(
            "Caller is not authorized to use the firewall helper",
            code="helper_caller_denied",
        )

    def handle(self, payload, peer_credentials=None):
        try:
            if peer_credentials is not None:
                self.authenticate(peer_credentials)
            request = validate_request(
                payload,
                expected_table=self.config.allowed_table,
                expected_interface=self.config.allowed_interface,
            )
            with self._lock:
                result = self._dispatch(request)
            return {
                "protocol": PROTOCOL_VERSION,
                "ok": True,
                "operation": request["operation"],
                "result": result,
            }
        except NetworkEnforcementError as exc:
            return {
                "protocol": PROTOCOL_VERSION,
                "ok": False,
                "operation": payload.get("operation")
                if isinstance(payload, dict)
                else "unknown",
                "error": exc.to_dict(),
            }
        except Exception as exc:  # defensive: never leak internals to callers
            return {
                "protocol": PROTOCOL_VERSION,
                "ok": False,
                "operation": payload.get("operation")
                if isinstance(payload, dict)
                else "unknown",
                "error": {
                    "code": "helper_internal_error",
                    "message": "The firewall helper could not complete the request",
                    "details": {"type": type(exc).__name__},
                },
            }

    @staticmethod
    def _target_from_request(request):
        target_data = request["target"]
        return DeviceTarget(
            device_id=target_data["device_id"],
            ip_address=target_data["ip_address"],
            mac_address=target_data["mac_address"],
            network_subnet=target_data["network_subnet"],
            interface=target_data["interface"],
            observation_id=target_data["observation_id"],
            observed_at=None,
            source=target_data["source"],
            evidence={"helper_validated": True},
        )

    def _dispatch(self, request):
        operation = request["operation"]
        if operation == "inspect_state":
            adapter = self._adapter_for(request)
            result = {
                "state": adapter.state_summary(),
                "recoverable_devices": self.store.recoverable_devices(),
                "nftables_available": True,
            }
            if "target" in request:
                result["snapshot"] = adapter.snapshot(
                    self._target_from_request(request)
                )
            return result

        target = self._target_from_request(request)
        device_id = target.device_id
        adapter = self._adapter_for(request)

        if operation == "verify_restriction":
            return {"verification": adapter.verify(target)}

        if operation == "apply_restriction":
            previous = adapter.snapshot(target)
            self.store.save(device_id, previous)
            try:
                result = adapter.block(target)
            except NetworkEnforcementError:
                rollback = self._safe_rollback(adapter, previous, target)
                raise HelperError(
                    "Restrictions could not be applied and verified",
                    code="helper_apply_failed",
                    details={"rollback": rollback},
                )
            result["pre_snapshot"] = previous
            return {"result": result}

        if operation == "restore_restriction":
            result = adapter.restore(target)
            if result.get("status") in ("restored", "not_applied"):
                self.store.delete(device_id)
            return {"result": result}

        if operation == "rollback_restriction":
            previous = request.get("snapshot") or self.store.load(device_id)
            if previous is None:
                raise HelperError(
                    "No saved Netra-owned state is available for rollback",
                    code="helper_snapshot_not_found",
                )
            result = adapter.rollback(previous, target)
            self.store.delete(device_id)
            return {"result": result}

        raise HelperError(
            "Unsupported helper operation", code="helper_operation_not_allowed"
        )

    @staticmethod
    def _safe_rollback(adapter, previous, target):
        try:
            return adapter.rollback(previous, target)
        except NetworkEnforcementError as exc:
            return {"status": "failed", "error": exc.to_dict()}


class _HelperHandler(socketserver.BaseRequestHandler):
    def handle(self):
        service = self.server.netra_service
        try:
            request = read_message(self.request)
        except NetworkEnforcementError as exc:
            response = {
                "protocol": PROTOCOL_VERSION,
                "ok": False,
                "operation": "unknown",
                "error": exc.to_dict(),
            }
            self._respond(response)
            return

        credentials = None
        if hasattr(socketserver, "UnixStreamServer"):
            credentials = self.request.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
            )
        response = service.handle(request, peer_credentials=credentials)
        self._respond(response)

    def _respond(self, response):
        try:
            self.request.sendall(encode_message(response))
        except OSError:
            pass


class _HelperServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    block_on_close = False

    def server_close(self):
        """Close the listener and unlink only the socket bound by this server."""
        try:
            # Bypass platform-specific UnixStreamServer.server_close() variants
            # so unlinking is always guarded by the bound socket's identity.
            socketserver.TCPServer.server_close(self)
        finally:
            self._threads.join()
            self._unlink_owned_socket()

    def _unlink_owned_socket(self):
        identity = getattr(self, "_owned_socket_identity", None)
        name = getattr(self, "_socket_name", None)
        dir_fd = getattr(self, "_socket_directory_fd", None)
        if identity is None or not name or dir_fd is None:
            return
        try:
            try:
                current = _path_identity(name, dir_fd=dir_fd)
            except FileNotFoundError:
                return
            except OSError as exc:
                raise HelperPermissionError(
                    "Helper socket could not be safely removed",
                    code="helper_socket_cleanup_failed",
                    details={"error": str(exc)},
                ) from exc
            if current != identity:
                return
            try:
                os.unlink(name, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise HelperPermissionError(
                    "Helper socket could not be safely removed",
                    code="helper_socket_cleanup_failed",
                    details={"error": str(exc)},
                ) from exc
        finally:
            try:
                os.close(dir_fd)
            except OSError:
                pass
            self._socket_directory_fd = None
            self._owned_socket_identity = None


def _configure_socket_permissions(server):
    """Restrict the bound socket to helper UID and the netra-backend GID."""
    name = server._socket_name
    dir_fd = server._socket_directory_fd
    if _path_identity(name, dir_fd=dir_fd) != server._owned_socket_identity:
        raise HelperPermissionError(
            "The helper socket path changed before permissions were applied",
            code="helper_socket_path_changed",
        )
    group_id = _resolve_socket_group()
    os.chown(
        name,
        os.getuid(),
        group_id,
        dir_fd=dir_fd,
        follow_symlinks=False,
    )
    os.chmod(
        name,
        HELPER_SOCKET_MODE,
        dir_fd=dir_fd,
        follow_symlinks=False,
    )


def build_server(config, service):
    """Create a bound server; callers must explicitly activate it."""
    parent = os.path.dirname(config.socket_path)
    if parent and not os.path.isdir(parent):
        raise ValueError("Helper socket directory does not exist")
    if os.path.exists(config.socket_path):
        raise ValueError("Helper socket path already exists")
    previous_umask = os.umask(0o077)
    server = None
    directory_fd = None
    try:
        directory_fd = os.open(parent or ".", os.O_RDONLY | os.O_DIRECTORY)
        server = _HelperServer(config.socket_path, _HelperHandler)
        server._socket_name = os.path.basename(config.socket_path)
        server._socket_directory_fd = directory_fd
        directory_fd = None  # ownership transferred to the server
        server._owned_socket_identity = _path_identity(
            server._socket_name, dir_fd=server._socket_directory_fd
        )
    except BaseException:
        if server is not None:
            server.server_close()
        if directory_fd is not None:
            os.close(directory_fd)
        raise
    finally:
        os.umask(previous_umask)
    server.netra_service = service
    try:
        _configure_socket_permissions(server)
    except HelperError:
        server.server_close()
        raise
    except OSError as exc:
        try:
            server.server_close()
        except HelperError as cleanup_exc:
            raise HelperPermissionError(
                "Helper socket permissions failed and cleanup also failed",
                code="helper_socket_cleanup_failed",
                details={
                    "setup_error": str(exc),
                    "cleanup_error": str(cleanup_exc),
                },
            ) from cleanup_exc
        raise HelperPermissionError(
            "Helper socket permissions could not be configured",
            code="helper_socket_permission_failed",
            details={"error": str(exc)},
        ) from exc
    return server


def main(argv=None):
    """Service entry point. Never called by the FastAPI backend."""
    try:
        config = HelperConfig.from_env()
        service = HelperService(config)
        server = build_server(config, service)
    except (ValueError, OSError, HelperError) as exc:
        print(f"netra-network-helper: {exc}", file=sys.stderr)
        return 1
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
