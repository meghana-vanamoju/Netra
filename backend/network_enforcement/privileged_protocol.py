"""Shared wire format and strict schema for the Netra privileged helper.

The backend never sends command strings through this protocol. It sends one of
the operations below plus already-validated target fields. The helper performs
its own validation before constructing any nftables command.
"""

import ipaddress
import json
import struct

from network_enforcement import commands
from network_enforcement.errors import HelperProtocolError

PROTOCOL_VERSION = 1
LENGTH_PREFIX_BYTES = 4
MAX_MESSAGE_BYTES = 64 * 1024

OPERATIONS = frozenset(
    {
        "inspect_state",
        "apply_restriction",
        "restore_restriction",
        "verify_restriction",
        "rollback_restriction",
    }
)
_TARGET_KEYS = {
    "device_id",
    "ip_address",
    "mac_address",
    "network_subnet",
    "interface",
    "source",
    "observation_id",
}


def normalize_socket_path(value):
    """Accept only a short, absolute, non-traversing Unix socket path."""
    if not isinstance(value, str) or not value.startswith("/") or "\x00" in value:
        raise HelperProtocolError("Invalid helper socket path", code="helper_socket_path_invalid")
    if len(value.encode()) > 107:
        raise HelperProtocolError("Helper socket path is too long", code="helper_socket_path_invalid")
    if any(part in ("", ".", "..") for part in value.split("/")[1:]):
        raise HelperProtocolError(
            "Helper socket path contains an invalid component",
            code="helper_socket_path_invalid",
        )
    return value


def encode_message(payload):
    """Serialize one length-prefixed JSON request or response."""
    try:
        raw = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HelperProtocolError(
            "Message is not JSON serializable", code="helper_protocol_error"
        ) from exc
    if not raw or len(raw) > MAX_MESSAGE_BYTES:
        raise HelperProtocolError(
            "Message length is outside the allowed range", code="helper_message_too_large"
        )
    return struct.pack("!I", len(raw)) + raw


def _recv_exactly(sock, size):
    chunks = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise HelperProtocolError(
                "Helper connection closed unexpectedly", code="helper_connection_closed"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_message(sock):
    """Read one bounded message from a connected Unix socket."""
    prefix = _recv_exactly(sock, LENGTH_PREFIX_BYTES)
    (length,) = struct.unpack("!I", prefix)
    if length < 2 or length > MAX_MESSAGE_BYTES:
        raise HelperProtocolError(
            "Message length is outside the allowed range", code="helper_message_too_large"
        )
    raw = _recv_exactly(sock, length)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HelperProtocolError(
            "Message is not valid JSON", code="helper_invalid_json"
        ) from exc
    if not isinstance(payload, dict):
        raise HelperProtocolError(
            "Message must be a JSON object", code="helper_invalid_request"
        )
    return payload


def _require_exact_keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise HelperProtocolError(
            f"{label} has an unexpected shape", code="helper_invalid_request"
        )


def validate_request(payload, *, expected_table=None, expected_interface=None):
    """Validate a request and return a normalized copy.

    ``expected_table`` and ``expected_interface`` are helper-owned settings.
    A request that disagrees with them is rejected even when its syntax is
    otherwise valid.
    """
    if not isinstance(payload, dict):
        raise HelperProtocolError(
            "Request must be a JSON object", code="helper_invalid_request"
        )
    operation = payload.get("operation")
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise HelperProtocolError(
            "Unsupported helper operation", code="helper_operation_not_allowed"
        )
    has_snapshot = "snapshot" in payload
    if operation == "inspect_state" and "target" not in payload:
        expected_top = {"protocol", "operation", "table"}
    else:
        expected_top = {"protocol", "operation", "table", "target"}
    if has_snapshot:
        expected_top.add("snapshot")
    _require_exact_keys(payload, expected_top, "Request")

    if payload["protocol"] != PROTOCOL_VERSION or isinstance(
        payload["protocol"], bool
    ):
        raise HelperProtocolError(
            "Unsupported helper protocol version", code="helper_protocol_mismatch"
        )
    if operation != "rollback_restriction" and has_snapshot:
        raise HelperProtocolError(
            "Snapshot is only valid for rollback", code="helper_invalid_request"
        )

    table = commands.validate_table_name(payload["table"])
    if expected_table is not None and table != expected_table:
        raise HelperProtocolError(
            "Request table is not permitted by this helper", code="helper_table_denied"
        )

    target = payload.get("target")
    if target is None:
        normalized = {
            "protocol": PROTOCOL_VERSION,
            "operation": operation,
            "table": table,
        }
        if has_snapshot:
            raise HelperProtocolError(
                "Snapshot requires a target", code="helper_invalid_request"
            )
        return normalized
    _require_exact_keys(target, _TARGET_KEYS, "Target")
    device_id = target["device_id"]
    if isinstance(device_id, bool) or not isinstance(device_id, int) or device_id <= 0:
        raise HelperProtocolError(
            "Target device_id must be a positive integer", code="helper_invalid_device"
        )
    ip_address = commands.validate_ipv4(target["ip_address"])
    mac_address = commands.validate_mac_address(target["mac_address"])
    interface = commands.validate_interface(target["interface"])
    if expected_interface is not None and interface != expected_interface:
        raise HelperProtocolError(
            "Request interface is not permitted by this helper",
            code="helper_interface_denied",
        )
    observation_id = target["observation_id"]
    if (
        isinstance(observation_id, bool)
        or not isinstance(observation_id, int)
        or observation_id <= 0
    ):
        raise HelperProtocolError(
            "Target observation_id must be a positive integer",
            code="helper_invalid_device",
        )

    try:
        subnet = ipaddress.ip_network(str(target["network_subnet"]), strict=False)
    except ValueError as exc:
        raise HelperProtocolError(
            "Target subnet is invalid", code="helper_invalid_subnet"
        ) from exc
    if (
        subnet.version != 4
        or subnet.prefixlen < 16
        or not subnet.is_private
        or ipaddress.ip_address(ip_address) not in subnet
    ):
        raise HelperProtocolError(
            "Target subnet is not a private IPv4 range containing the device",
            code="helper_invalid_subnet",
        )

    source = target["source"]
    expected_source = f"hotspot:{interface}"
    if not isinstance(source, str) or source != expected_source:
        raise HelperProtocolError(
            "Target observation must come from the configured hotspot",
            code="helper_invalid_source",
        )

    normalized = {
        "protocol": PROTOCOL_VERSION,
        "operation": operation,
        "table": table,
        "target": {
            "device_id": device_id,
            "ip_address": ip_address,
            "mac_address": mac_address,
            "network_subnet": str(subnet),
            "interface": interface,
            "source": source,
            "observation_id": observation_id,
        },
    }
    if has_snapshot:
        snapshot = payload["snapshot"]
        if not isinstance(snapshot, dict):
            raise HelperProtocolError(
                "Snapshot must be a JSON object", code="helper_invalid_snapshot"
            )
        normalized["snapshot"] = snapshot
    return normalized


def validate_response(payload, *, operation=None):
    """Validate a helper response before the backend trusts it."""
    if not isinstance(payload, dict) or set(payload) not in (
        {"protocol", "ok", "operation", "result"},
        {"protocol", "ok", "operation", "error"},
    ):
        raise HelperProtocolError(
            "Helper response has an unexpected shape", code="helper_invalid_response"
        )
    if payload["protocol"] != PROTOCOL_VERSION or isinstance(
        payload["protocol"], bool
    ):
        raise HelperProtocolError(
            "Helper response uses an unsupported protocol version",
            code="helper_protocol_mismatch",
        )
    if operation is not None and payload["operation"] != operation:
        raise HelperProtocolError(
            "Helper response does not match the request", code="helper_invalid_response"
        )
    if not isinstance(payload["ok"], bool):
        raise HelperProtocolError(
            "Helper response ok flag is invalid", code="helper_invalid_response"
        )
    if payload["ok"]:
        result = payload["result"]
        if not isinstance(result, dict):
            raise HelperProtocolError(
                "Helper result must be a JSON object", code="helper_invalid_response"
            )
        return True, result
    error = payload["error"]
    if not isinstance(error, dict) or set(error) != {"code", "message", "details"}:
        raise HelperProtocolError(
            "Helper error has an unexpected shape", code="helper_invalid_response"
        )
    if not isinstance(error["code"], str) or not isinstance(error["message"], str):
        raise HelperProtocolError(
            "Helper error fields are invalid", code="helper_invalid_response"
        )
    if not isinstance(error["details"], dict):
        raise HelperProtocolError(
            "Helper error details must be an object", code="helper_invalid_response"
        )
    return False, error
