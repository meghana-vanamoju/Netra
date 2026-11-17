"""DNS provider registry and configuration selection."""

from dns.providers.adguard import AdGuardHomeAdapter
from dns.providers.config import ProviderConfig, public_config
from dns.providers.errors import ProviderNotConfigured
from dns.providers.pihole import PiHoleAdapter


def resolve_config(config: ProviderConfig | None = None) -> ProviderConfig:
    return config or ProviderConfig.from_env()


def get_provider(config: ProviderConfig | None = None):
    cfg = resolve_config(config)
    backend = cfg.backend
    if backend not in {"adguard", "pihole"}:
        if cfg.adguard_configured:
            backend = "adguard"
        elif cfg.pihole_configured:
            backend = "pihole"
        else:
            return None
    if backend == "adguard":
        if not cfg.adguard_configured:
            return None
        return AdGuardHomeAdapter(
            url=cfg.adguard_url,
            username=cfg.adguard_username,
            password=cfg.adguard_password,
            timeout=cfg.adguard_timeout,
            connect_timeout=cfg.adguard_connect_timeout,
            page_size=cfg.adguard_page_size,
            max_events=cfg.adguard_max_events,
        )
    if not cfg.pihole_configured:
        return None
    return PiHoleAdapter(
        url=cfg.pihole_url, token=cfg.pihole_token, timeout=cfg.adguard_timeout,
        max_events=cfg.adguard_max_events,
    )


def provider_status(config: ProviderConfig | None = None) -> dict:
    cfg = resolve_config(config)
    result = {
        "provider": None,
        "state": "not_configured",
        "message": "No DNS provider is configured.",
        "capabilities": [],
        "unsupported": [],
        "config": public_config(cfg),
    }
    provider = get_provider(cfg)
    if provider is None:
        return result
    health = provider.health()
    health["config"] = public_config(cfg)
    return health


def provider_statistics(config: ProviderConfig | None = None) -> dict:
    cfg = resolve_config(config)
    provider = get_provider(cfg)
    if provider is None or not hasattr(provider, "statistics"):
        raise ProviderNotConfigured("No DNS provider with statistics support is configured")
    return provider.statistics()


def provider_filtering(config: ProviderConfig | None = None) -> dict:
    cfg = resolve_config(config)
    provider = get_provider(cfg)
    if provider is None or not hasattr(provider, "filtering_status"):
        raise ProviderNotConfigured("No DNS provider with filtering support is configured")
    return provider.filtering_status()


def fetch_provider_queries(config: ProviderConfig | None = None) -> list:
    cfg = resolve_config(config)
    provider = get_provider(cfg)
    if provider is None:
        raise ProviderNotConfigured("No DNS provider is configured")
    return provider.fetch_queries(max_events=cfg.adguard_max_events)
