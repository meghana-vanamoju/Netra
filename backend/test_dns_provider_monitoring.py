import json
from datetime import datetime
from unittest.mock import patch

import httpx
import pytest

from dns.providers.adguard import (
    AdGuardHomeAdapter,
    normalize_domain,
    parse_provider_time,
)
from dns.providers.config import ProviderConfig
from dns.providers.errors import (
    ProviderMalformedResponse,
    ProviderNotConfigured,
    ProviderTimeout,
    ProviderUnauthorized,
    ProviderUnavailable,
    ProviderUnreachable,
    ProviderUnsupported,
)
from dns.providers.pihole import PiHoleAdapter
from dns.providers.registry import get_provider, provider_status


class FakeResponse:
    def __init__(self, payload=None, status_code=200, invalid_json=False):
        self.payload = payload
        self.status_code = status_code
        self.invalid_json = invalid_json

    def json(self):
        if self.invalid_json:
            raise ValueError("no json")
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)


def sample_query(domain="ads.doubleclick.net", blocked=False, stamp=None):
    return {
        "question": {"name": domain, "type": "A", "class": "IN"},
        "client": "192.168.29.30",
        "client_info": {"name": "phone", "whois": {}},
        "time": stamp or "2026-11-17T10:11:12.123456789Z",
        "status": "NOERROR",
        "reason": "FilteredBlackList" if blocked else "NotFilteredNotFound",
        "rules": ["||ads.doubleclick.net^"] if blocked else [],
        "upstream": "https://dns.example/dns-query",
    }


def test_domain_and_timestamp_normalization():
    assert normalize_domain("  ADS.DoubleClick.NET. ") == "ads.doubleclick.net"
    assert normalize_domain("not a domain") is None
    assert normalize_domain("localhost") is None
    assert parse_provider_time("2026-11-17T10:11:12.123456789Z") == datetime(
        2026, 11, 17, 10, 11, 12, 123456
    )


def test_adguard_not_configured():
    adapter = AdGuardHomeAdapter()
    assert adapter.available() is False
    with pytest.raises(ProviderNotConfigured):
        adapter.query_log()
    assert adapter.health()["state"] == "not_configured"


@pytest.mark.parametrize(
    "response,expected",
    [
        (FakeResponse(status_code=401), ProviderUnauthorized),
        (FakeResponse(status_code=404), ProviderUnsupported),
        (FakeResponse(status_code=503), ProviderUnavailable),
        (FakeResponse(invalid_json=True), ProviderMalformedResponse),
    ],
)
def test_adguard_error_states(response, expected):
    adapter = AdGuardHomeAdapter("http://127.0.0.1:3001", "u", "p")
    with patch("dns.providers.adguard.httpx.get", return_value=response):
        with pytest.raises(expected):
            adapter._get_json("/control/status")


def test_adguard_timeout_and_unreachable():
    adapter = AdGuardHomeAdapter("http://127.0.0.1:3001")
    with patch("dns.providers.adguard.httpx.get", side_effect=httpx.TimeoutException("slow")):
        with pytest.raises(ProviderTimeout):
            adapter._get_json("/control/status")
    with patch("dns.providers.adguard.httpx.get", side_effect=httpx.ConnectError("down")):
        with pytest.raises(ProviderUnreachable):
            adapter._get_json("/control/status")


def test_adguard_query_log_normalization_and_dedup():
    adapter = AdGuardHomeAdapter("http://127.0.0.1:3001")
    page = {
        "data": [
            sample_query(blocked=True),
            sample_query(domain="sentry.io", blocked=False, stamp="2026-11-17T10:11:11Z"),
            sample_query(domain="bad domain"),
            {"unexpected": True},
        ]
    }
    with patch("dns.providers.adguard.httpx.get", return_value=FakeResponse(page)):
        records = adapter.query_log(limit=10)
    assert len(records) == 2
    first = records[0]
    assert first["domain"] == "ads.doubleclick.net"
    assert first["client"] == "192.168.29.30"
    assert first["client_name"] == "phone"
    assert first["query_type"] == "A"
    assert first["blocked"] is True
    assert first["source"] == "adguard-home"
    assert len(first["source_event_id"]) == 32
    assert records[1]["blocked"] is False


def test_adguard_fetch_queries_is_bounded_and_deduplicated():
    adapter = AdGuardHomeAdapter("http://127.0.0.1:3001", page_size=2)
    first = {"data": [sample_query("a.example"), sample_query("b.example")]}
    second = {
        "data": [
            sample_query("a.example"),
            sample_query("c.example", stamp="2026-11-17T10:11:13Z"),
        ]
    }
    with patch(
        "dns.providers.adguard.httpx.get",
        side_effect=[FakeResponse(first), FakeResponse(second), FakeResponse({"data": []})],
    ):
        records = adapter.fetch_queries(max_events=10, page_size=2)
    assert [record["domain"] for record in records] == [
        "a.example",
        "b.example",
        "c.example",
    ]


def test_adguard_health_reports_real_capabilities():
    adapter = AdGuardHomeAdapter(
        "http://127.0.0.1:3001", "unique-user-marker", "unique-password-marker"
    )
    responses = [
        FakeResponse({"version": "v0.107.50", "protection_enabled": True}),
        FakeResponse({"data": [sample_query()]}),
        FakeResponse({"num_dns_queries": 4, "num_blocked_filtering": 1}),
        FakeResponse({"enabled": True, "user_rules": [], "filters": []}),
    ]
    with patch("dns.providers.adguard.httpx.get", side_effect=responses):
        health = adapter.health()
    assert health["state"] == "healthy"
    assert health["version"] == "v0.107.50"
    assert {"query_log", "statistics", "filtering"}.issubset(health["capabilities"])
    assert health["authentication"] == "configured"
    assert "unique-user-marker" not in json.dumps(health)
    assert "unique-password-marker" not in json.dumps(health)


def test_adguard_rule_helpers_are_validated_and_credential_free():
    adapter = AdGuardHomeAdapter("http://127.0.0.1:3001", "u", "p")
    with patch.object(
        adapter,
        "filtering_status",
        return_value={"enabled": True, "user_rules": [], "filter_count": 0},
    ), patch("dns.providers.adguard.httpx.post", return_value=FakeResponse({})) as post:
        result = adapter.add_user_rule("tracker.example")
        assert result["status"] == "applied"
        assert post.call_args.kwargs["json"] == {"rules": ["||tracker.example^"]}
    with patch.object(
        adapter,
        "filtering_status",
        return_value={
            "enabled": True,
            "user_rules": ["||tracker.example^"],
            "filter_count": 0,
        },
    ), patch("dns.providers.adguard.httpx.post", return_value=FakeResponse({})) as post:
        adapter.remove_user_rule("tracker.example")
        assert post.call_args.kwargs["json"] == {"rules": []}
    with pytest.raises(ValueError):
        adapter.add_user_rule("not a domain")


def test_adguard_set_rules_accepts_empty_success_body():
    adapter = AdGuardHomeAdapter("http://127.0.0.1:3001", "u", "p")
    empty = FakeResponse({})
    empty.content = b""
    with patch.object(
        adapter,
        "filtering_status",
        return_value={"enabled": True, "user_rules": [], "filter_count": 0},
    ), patch("dns.providers.adguard.httpx.post", return_value=empty):
        assert adapter.add_user_rule("tracker.example")["status"] == "applied"


def test_adguard_blocked_evidence_uses_provider_reason():
    adapter = AdGuardHomeAdapter("http://127.0.0.1:3001")
    normalized = AdGuardHomeAdapter._normalize_query(sample_query(blocked=True))
    with patch.object(adapter, "query_log", return_value=[normalized]):
        evidence = adapter.blocked_evidence("ads.doubleclick.net")
    assert evidence["blocked"] is True
    assert evidence["evidence"] == "FilteredBlackList"


def test_pihole_adapter_and_provider_switching():
    pihole = PiHoleAdapter("http://127.0.0.1:8080", "token")
    body = {
        "queries": [
            {
                "domain": "tracker.example",
                "timestamp": 1794900000,
                "client": "192.168.29.30",
                "status": "blocked_gravity",
            }
        ]
    }
    with patch("dns.providers.pihole.httpx.get", return_value=FakeResponse(body)):
        records = pihole.query_log(limit=10)
        health = pihole.health()
    assert records[0]["domain"] == "tracker.example"
    assert records[0]["blocked"] is True
    assert records[0]["source"] == "pihole"
    assert health["state"] == "healthy"

    config = ProviderConfig.from_env()
    object.__setattr__(config, "backend", "pihole")
    object.__setattr__(config, "pihole_url", "http://127.0.0.1:8080")
    object.__setattr__(config, "pihole_token", "token")
    assert isinstance(get_provider(config), PiHoleAdapter)


def test_provider_status_never_contains_secrets(monkeypatch):
    monkeypatch.setenv("NETRA_ADGUARD_API_URL", "http://127.0.0.1:3001")
    monkeypatch.setenv("NETRA_ADGUARD_USERNAME", "secret-user")
    monkeypatch.setenv("NETRA_ADGUARD_PASSWORD", "secret-password")
    monkeypatch.setenv("NETRA_DNS_BACKEND", "adguard")
    with patch.object(
        AdGuardHomeAdapter,
        "health",
        return_value={
            "state": "healthy",
            "provider": "adguard-home",
            "capabilities": [],
            "unsupported": [],
            "config": {},
        },
    ):
        report = provider_status()
    assert report["config"]["adguard_authenticated"] is True
    assert "secret-password" not in json.dumps(report)
    assert "secret-user" not in json.dumps(report)
