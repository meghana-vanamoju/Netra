"""Opt-in configuration for per-device network enforcement.

Nothing in this module enables enforcement implicitly. The defaults are always
disabled and dry-run; invalid values fall back to the safest option and are
reported as warnings instead of being partially applied.
"""

import os
import re
from dataclasses import dataclass

DEFAULT_TABLE = "netra"
DEFAULT_COMMAND_TIMEOUT_SECONDS = 3.0
DEFAULT_OBSERVATION_TTL_SECONDS = 300
DEFAULT_HELPER_SOCKET_PATH = "/run/netra/network-enforcement.sock"

TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
INTERFACE_PATTERN = re.compile(r"^[A-Za-z0-9_.:@-]{1,32}$")

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _parse_bool(env, name, default, warnings):
    raw = env.get(name)
    if raw is None or not str(raw).strip():
        return default
    value = str(raw).strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    warnings.append(f"{name} must be true/false; using {str(default).lower()}")
    return default


def _parse_float(env, name, default, low, high, warnings):
    raw = env.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        warnings.append(f"{name} must be a number; using {default}")
        return default
    if not low <= value <= high:
        warnings.append(f"{name} must be between {low} and {high}; using {default}")
        return default
    return value


def _parse_int(env, name, default, low, high, warnings):
    raw = env.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        warnings.append(f"{name} must be an integer; using {default}")
        return default
    if not low <= value <= high:
        warnings.append(f"{name} must be between {low} and {high}; using {default}")
        return default
    return value


def _parse_name(env, name, default, pattern, warnings):
    raw = env.get(name)
    if raw is None or not str(raw).strip():
        return default
    value = str(raw).strip()
    if not pattern.fullmatch(value):
        warnings.append(f"{name} contains unsupported characters; using {default!r}")
        return default
    return value


def _parse_socket_path(env, name, default, warnings):
    raw = env.get(name)
    if raw is None or not str(raw).strip():
        return default
    value = str(raw).strip()
    if (
        not value.startswith("/")
        or "\x00" in value
        or len(value.encode()) > 107
        or any(part in ("", ".", "..") for part in value.split("/")[1:])
    ):
        warnings.append(f"{name} is not a safe absolute Unix socket path; using default")
        return default
    return value


@dataclass(frozen=True)
class NetworkEnforcementConfig:
    enabled: bool
    dry_run: bool
    table: str
    interface: str | None
    ifb: str | None
    command_timeout_seconds: float
    observation_ttl_seconds: int
    warnings: tuple[str, ...] = ()
    helper_socket_path: str = DEFAULT_HELPER_SOCKET_PATH
    helper_timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS

    @property
    def apply_permitted(self) -> bool:
        return self.enabled and not self.dry_run

    @property
    def helper_required(self) -> bool:
        return self.enabled

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "apply_permitted": self.apply_permitted,
            "table": self.table,
            "interface": self.interface,
            "ifb": self.ifb,
            "command_timeout_seconds": self.command_timeout_seconds,
            "observation_ttl_seconds": self.observation_ttl_seconds,
            "warnings": list(self.warnings),
            "helper_required": self.helper_required,
            "helper_socket_path": self.helper_socket_path,
            "helper_timeout_seconds": self.helper_timeout_seconds,
        }

    @classmethod
    def from_env(cls, environ=None):
        env = environ if environ is not None else os.environ
        warnings = []
        enabled = _parse_bool(
            env, "NETRA_NETWORK_ENFORCEMENT_ENABLED", False, warnings
        )
        dry_run = _parse_bool(
            env, "NETRA_NETWORK_ENFORCEMENT_DRY_RUN", True, warnings
        )
        table = _parse_name(
            env,
            "NETRA_NETWORK_ENFORCEMENT_TABLE",
            DEFAULT_TABLE,
            TABLE_NAME_PATTERN,
            warnings,
        )
        interface = _parse_name(
            env,
            "NETRA_NETWORK_ENFORCEMENT_INTERFACE",
            None,
            INTERFACE_PATTERN,
            warnings,
        )
        ifb = _parse_name(
            env, "NETRA_NETWORK_ENFORCEMENT_IFB", None, INTERFACE_PATTERN, warnings
        )
        timeout = _parse_float(
            env,
            "NETRA_NETWORK_ENFORCEMENT_COMMAND_TIMEOUT_SECONDS",
            DEFAULT_COMMAND_TIMEOUT_SECONDS,
            0.5,
            30.0,
            warnings,
        )
        ttl = _parse_int(
            env,
            "NETRA_NETWORK_ENFORCEMENT_OBSERVATION_TTL_SECONDS",
            DEFAULT_OBSERVATION_TTL_SECONDS,
            30,
            86400,
            warnings,
        )
        helper_socket = _parse_socket_path(
            env,
            "NETRA_NETWORK_ENFORCEMENT_HELPER_SOCKET",
            DEFAULT_HELPER_SOCKET_PATH,
            warnings,
        )
        helper_timeout = _parse_float(
            env,
            "NETRA_NETWORK_ENFORCEMENT_HELPER_TIMEOUT_SECONDS",
            DEFAULT_COMMAND_TIMEOUT_SECONDS,
            0.5,
            30.0,
            warnings,
        )
        return cls(
            enabled=enabled,
            dry_run=dry_run,
            table=table,
            interface=interface,
            ifb=ifb,
            command_timeout_seconds=timeout,
            observation_ttl_seconds=ttl,
            warnings=tuple(warnings),
            helper_socket_path=helper_socket,
            helper_timeout_seconds=helper_timeout,
        )
