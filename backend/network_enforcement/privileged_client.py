"""Unprivileged backend client for the Netra firewall helper."""

import socket

from network_enforcement.config import NetworkEnforcementConfig
from network_enforcement.errors import (
    HelperError,
    HelperPermissionError,
    HelperProtocolError,
    HelperTimeoutError,
    HelperUnavailableError,
)
from network_enforcement.target import DeviceTarget
from network_enforcement.privileged_protocol import (
    OPERATIONS,
    PROTOCOL_VERSION,
    encode_message,
    normalize_socket_path,
    read_message,
    validate_response,
)


class HelperClient:
    """Send only allowlisted operations over a local Unix-domain socket."""

    def __init__(self, socket_path, timeout_seconds=3.0, table=None):
        self.socket_path = normalize_socket_path(socket_path)
        self.timeout_seconds = float(timeout_seconds)
        self.table = table

    def probe(self):
        """Read-only readiness probe; never changes firewall state."""
        return self.call("inspect_state")

    def call(self, operation, *, target=None, snapshot=None):
        if operation not in OPERATIONS:
            raise HelperProtocolError(
                "Unsupported helper operation", code="helper_operation_not_allowed"
            )
        table = target.table if target is not None else self.table
        if not isinstance(table, str) or not table:
            raise HelperProtocolError(
                "A Netra table is required for helper requests",
                code="helper_invalid_request",
            )
        request = {
            "protocol": PROTOCOL_VERSION,
            "operation": operation,
            "table": table,
        }
        if target is not None:
            request["target"] = target.to_request()
        if snapshot is not None:
            request["snapshot"] = snapshot
        return self._exchange(request, operation)

    def call_raw(self, request, *, operation=None):
        """Send an already-constructed request (used by the readiness probe)."""
        return self._exchange(request, operation)

    def _exchange(self, request, operation):
        raw = encode_message(request)
        sock = None
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(self.timeout_seconds)
            sock.connect(self.socket_path)
            sock.sendall(raw)
            payload = read_message(sock)
        except FileNotFoundError as exc:
            raise HelperUnavailableError(
                "The Netra firewall helper is not available",
                code="helper_unavailable",
            ) from exc
        except PermissionError as exc:
            raise HelperPermissionError(
                "The backend is not authorized to use the Netra firewall helper",
                code="helper_permission_denied",
            ) from exc
        except socket.timeout as exc:
            raise HelperTimeoutError(
                "The Netra firewall helper timed out",
                code="helper_timeout",
            ) from exc
        except HelperError:
            raise
        except OSError as exc:
            raise HelperUnavailableError(
                "The Netra firewall helper could not be reached",
                code="helper_unavailable",
                details={"error": str(exc)},
            ) from exc
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass

        ok, value = validate_response(payload, operation=operation)
        if not ok:
            raise HelperError(
                value["message"], code=value["code"], details=value["details"]
            )
        return value


class HelperTarget:
    """A validated request target paired with its helper-owned table."""

    def __init__(self, device_target: DeviceTarget, table: str):
        self.device = device_target
        self.table = table

    def to_request(self):
        return {
            "device_id": self.device.device_id,
            "ip_address": self.device.ip_address,
            "mac_address": self.device.mac_address,
            "network_subnet": self.device.network_subnet,
            "interface": self.device.interface,
            "source": self.device.source,
            "observation_id": self.device.observation_id,
        }


class HelperNftablesAdapter:
    """Adapter implementation whose effects occur only in the helper process."""

    def __init__(self, config: NetworkEnforcementConfig, client: HelperClient | None = None):
        self.config = config
        self.client = client or HelperClient(
            config.helper_socket_path, config.helper_timeout_seconds
        )

    def _wrap(self, target: DeviceTarget):
        if target.observation_id is None:
            raise HelperProtocolError(
                "A fresh observation is required before helper enforcement",
                code="helper_invalid_device",
            )
        return HelperTarget(target, self.config.table)

    def snapshot(self, target: DeviceTarget | None = None):
        if target is None:
            return self.client.probe()["state"]
        return self.client.call("inspect_state", target=self._wrap(target))["snapshot"]

    def block(self, target: DeviceTarget):
        return self.client.call("apply_restriction", target=self._wrap(target))["result"]

    def restore(self, target: DeviceTarget, *, handles=None):
        result = self.client.call(
            "restore_restriction", target=self._wrap(target)
        )["result"]
        if handles is not None:
            result["requested_handles"] = list(handles)
        return result

    def verify(self, target: DeviceTarget):
        return self.client.call(
            "verify_restriction", target=self._wrap(target)
        )["verification"]

    def rollback(self, previous, target: DeviceTarget):
        return self.client.call(
            "rollback_restriction", target=self._wrap(target), snapshot=previous
        )["result"]

    def state_summary(self):
        return self.client.probe()["state"]
