"""Environment-driven DNS provider configuration.

Secrets stay in environment variables and are never exposed by status or API
responses. The legacy router-adapter variables are reused for AdGuard Home so
existing lab configuration keeps working.
"""

import os
from dataclasses import dataclass

DEFAULT_TIMEOUT = 5.0
DEFAULT_CONNECT_TIMEOUT = 3.0
DEFAULT_MAX_EVENTS = 500
DEFAULT_PAGE_SIZE = 100


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, ""))
        return value if 0 < value <= 60 else default
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
        return value if low <= value <= high else default
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ProviderConfig:
    backend: str
    adguard_url: str | None
    adguard_username: str | None
    adguard_password: str | None
    adguard_timeout: float
    adguard_connect_timeout: float
    adguard_max_events: int
    adguard_page_size: int
    pihole_url: str | None
    pihole_token: str | None
    enforcement_enabled: bool
    dns_port: int

    @classmethod
    def from_env(cls) -> "ProviderConfig":
        backend = os.environ.get("NETRA_DNS_BACKEND", "").strip().lower()
        return cls(
            backend=backend,
            adguard_url=(os.environ.get("NETRA_ADGUARD_DNS_URL")
                         or os.environ.get("NETRA_ADGUARD_API_URL") or "").strip() or None,
            adguard_username=(os.environ.get("NETRA_ADGUARD_USERNAME") or "").strip() or None,
            adguard_password=os.environ.get("NETRA_ADGUARD_PASSWORD") or None,
            adguard_timeout=_float_env("NETRA_ADGUARD_TIMEOUT", DEFAULT_TIMEOUT),
            adguard_connect_timeout=_float_env(
                "NETRA_ADGUARD_CONNECT_TIMEOUT", DEFAULT_CONNECT_TIMEOUT
            ),
            adguard_max_events=_int_env(
                "NETRA_ADGUARD_MAX_EVENTS", DEFAULT_MAX_EVENTS, 1, 5000
            ),
            adguard_page_size=_int_env(
                "NETRA_ADGUARD_PAGE_SIZE", DEFAULT_PAGE_SIZE, 1, 500
            ),
            pihole_url=(os.environ.get("NETRA_PIHOLE_URL") or "").strip() or None,
            pihole_token=os.environ.get("NETRA_PIHOLE_TOKEN") or None,
            enforcement_enabled=os.environ.get(
                "NETRA_DNS_ENFORCEMENT_ENABLED", ""
            ).strip().lower() in {"1", "true", "yes", "on"},
            dns_port=_int_env("NETRA_ADGUARD_DNS_PORT", 53, 1, 65535),
        )

    @property
    def adguard_configured(self) -> bool:
        return bool(self.adguard_url)

    @property
    def pihole_configured(self) -> bool:
        return bool(self.pihole_url and self.pihole_token)


def public_config(config: ProviderConfig) -> dict:
    """Return configuration metadata with no secret material."""
    return {
        "backend": config.backend or None,
        "adguard_configured": config.adguard_configured,
        "pihole_configured": config.pihole_configured,
        "adguard_authenticated": bool(config.adguard_username and config.adguard_password),
        "enforcement_enabled": config.enforcement_enabled,
        "max_events": config.adguard_max_events,
    }
