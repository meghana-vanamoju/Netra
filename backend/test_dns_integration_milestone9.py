import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

os.environ["NETRA_DB_PATH"] = os.path.join(
    tempfile.mkdtemp(), "dns-milestone9.db"
)

from fastapi.testclient import TestClient

from db.models import Device, DNSEvent, Policy
from db.session import get_session_factory, init_db
from main import app

init_db()
client = TestClient(app)

M9_DOMAINS = {
    "m9-ads.doubleclick.net",
    "m9-analytics.google-analytics.com",
    "m9-telemetry.sentry.io",
    "m9-unknown.example.com",
}

REAL_RECORDS = [
    {
        "domain": "m9-ads.doubleclick.net",
        "query_type": "A",
        "client": "192.168.29.30",
        "client_name": "phone",
        "timestamp": datetime(2026, 11, 17, 10, 0, 1),
        "status": "NOERROR",
        "reason": "FilteredBlackList",
        "blocked": True,
        "rules": ["||m9-ads.doubleclick.net^"],
        "upstream": None,
        "source": "adguard-home",
        "source_event_id": "m9-real-1",
    },
    {
        "domain": "m9-analytics.google-analytics.com",
        "query_type": "A",
        "client": "192.168.29.30",
        "client_name": "phone",
        "timestamp": datetime(2026, 11, 17, 10, 0, 2),
        "status": "NOERROR",
        "reason": "NotFilteredNotFound",
        "blocked": False,
        "rules": [],
        "upstream": "https://dns.example/dns-query",
        "source": "adguard-home",
        "source_event_id": "m9-real-2",
    },
    {
        "domain": "m9-telemetry.sentry.io",
        "query_type": "A",
        "client": "192.168.29.4",
        "client_name": None,
        "timestamp": datetime(2026, 11, 17, 10, 0, 3),
        "status": "NOERROR",
        "reason": "NotFilteredNotFound",
        "blocked": False,
        "rules": [],
        "upstream": None,
        "source": "adguard-home",
        "source_event_id": "m9-real-3",
    },
    {
        "domain": "m9-unknown.example.com",
        "query_type": "A",
        "client": "192.168.29.30",
        "client_name": "phone",
        "timestamp": datetime(2026, 11, 17, 10, 0, 4),
        "status": "NOERROR",
        "reason": "NotFilteredNotFound",
        "blocked": False,
        "rules": [],
        "upstream": None,
        "source": "adguard-home",
        "source_event_id": "m9-real-4",
    },
]


def healthy_status():
    return {
        "provider": "adguard-home",
        "state": "healthy",
        "message": "Provider is reachable and responding.",
        "capabilities": ["api_connectivity", "authentication", "query_log"],
        "unsupported": [],
    }


def test_provider_statistics_and_filtering_endpoints():
    stats = {
        "total_queries": 35,
        "blocked_queries": 12,
        "top_queried_domains": [],
        "top_blocked_domains": [],
        "top_clients": [],
    }
    filtering = {"enabled": True, "user_rules": [], "filter_count": 2}
    with patch("api_dns.provider_statistics", return_value=stats):
        assert client.get("/api/dns/providers/statistics").json() == stats
    with patch("api_dns.provider_filtering", return_value=filtering):
        assert client.get("/api/dns/providers/filtering").json() == filtering


def test_provider_sync_is_idempotent_and_failure_recovers():
    with patch("api_dns.provider_status", return_value=healthy_status()), patch(
        "api_dns.fetch_provider_queries", return_value=REAL_RECORDS
    ):
        first = client.post("/api/dns/events/sync")
        assert first.status_code == 200
        assert first.json() == {
            "provider": "adguard-home",
            "fetched": 4,
            "inserted": 4,
            "duplicates": 0,
            "skipped": 0,
            "state": "healthy",
        }
        second = client.post("/api/dns/events/sync")
        assert second.status_code == 200
        assert second.json()["inserted"] == 0
        assert second.json()["duplicates"] == 4

    events = client.get("/api/dns/events?limit=500").json()
    mine = [event for event in events if event["domain"] in M9_DOMAINS]
    assert len(mine) == 4
    assert all(event["source"] == "adguard-home" for event in mine)
    assert all(event["query_type"] == "A" for event in mine)
    assert any(event["blocked"] is True for event in events)

    summary = client.get("/api/dns/analytics/summary").json()
    assert summary["total"] >= 4
    assert summary["unique_domains"] >= 4
    assert summary["blocked"] >= 1
    assert summary["allowed"] >= 3
    assert summary["blocking_percentage"] is not None
    assert summary["by_category"]["Advertising"] >= 1
    assert summary["by_category"]["Tracking/Analytics"] >= 1
    assert summary["by_category"]["Telemetry"] >= 1
    assert summary["by_category"]["Unknown"] >= 1
    assert any(item["domain"] == "m9-ads.doubleclick.net" for item in summary["top_blocked_domains"])
    assert summary["by_client"][0]["client"] == "192.168.29.30"
    assert summary["by_source"]["adguard-home"] >= 4
    assert summary["timeline"]

    with patch(
        "api_dns.provider_status",
        return_value={"provider": "adguard-home", "state": "unreachable"},
    ):
        failed = client.post("/api/dns/events/sync")
    assert failed.status_code == 503
    assert failed.json()["detail"]["state"] == "unreachable"

    with patch("api_dns.provider_status", return_value=healthy_status()), patch(
        "api_dns.fetch_provider_queries", return_value=REAL_RECORDS
    ):
        recovered = client.post("/api/dns/events/sync")
    assert recovered.status_code == 200
    assert recovered.json()["duplicates"] == 4
    assert client.get("/api/dns/analytics/summary").json()["total"] >= 4


def test_legacy_inventory_and_events_are_preserved():
    db = get_session_factory()()
    device = db.query(Device).filter(Device.ip_address == "10.252.213.78").first()
    if not device:
        device = Device(ip_address="10.252.213.78", hostname="office-legacy")
        db.add(device)
        db.commit()
    db.add(
        DNSEvent(
            domain="legacy.example",
            category="Unknown",
            device_id=device.id,
            source="synthetic-demo",
        )
    )
    db.commit()
    db.close()
    with patch("api_dns.provider_status", return_value=healthy_status()), patch(
        "api_dns.fetch_provider_queries", return_value=REAL_RECORDS
    ):
        assert client.post("/api/dns/events/sync").status_code == 200
    domains = [item["domain"] for item in client.get("/api/dns/events?limit=500").json()]
    assert "legacy.example" in domains
    assert "m9-ads.doubleclick.net" in domains


def test_consent_enforcement_verification_and_rollback():
    db = get_session_factory()()
    policy = Policy(
        name="Block observed tracking",
        description="Reason: frequent tracking/telemetry queries",
        target=None,
        action="block_domain_category",
        risk="Medium",
        reversible=1,
        status="dry-run completed",
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    pid = policy.id
    db.close()

    dry = client.post("/api/policies/dry-run", json=[pid])
    assert dry.status_code == 200
    plan = dry.json()["plan"]
    assert "m9-analytics.google-analytics.com" in plan["domains"]
    assert "m9-ads.doubleclick.net" in plan["domains"]
    assert "m9-unknown.example.com" not in plan["domains"]
    plan_id = dry.json()["plan_id"]

    no_confirm = client.post(
        f"/api/policies/{pid}/approve", params={"plan_id": plan_id, "confirm": False}
    )
    assert no_confirm.status_code == 400
    approved = client.post(
        f"/api/policies/{pid}/approve", params={"plan_id": plan_id, "confirm": True}
    )
    assert approved.status_code == 200

    disabled_adapter = MagicMock()
    disabled_adapter.available.return_value = True
    disabled_adapter.enabled = False
    disabled_adapter.backend = "adguard"
    with patch("api_consent.DNSBackendAdapter", return_value=disabled_adapter):
        denied = client.post(f"/api/policies/{pid}/apply")
    assert denied.status_code == 503

    adapter = MagicMock()
    adapter.available.return_value = True
    adapter.enabled = True
    adapter.backend = "adguard"
    adapter.provider.filtering_status.return_value = {
        "enabled": True,
        "user_rules": [],
        "filter_count": 0,
    }
    adapter.apply_policy.return_value = {
        "status": "applied",
        "provider": "adguard",
        "domains": plan["domains"],
    }
    with patch("api_consent.DNSBackendAdapter", return_value=adapter):
        applied = client.post(f"/api/policies/{pid}/apply")
    assert applied.status_code == 200
    body = applied.json()
    assert body["status"] == "applied"
    assert body["consent"]["approver"] == "local-user"
    snapshot_id = body["snapshot_id"]
    adapter.apply_policy.assert_called_once()
    applied_domains = adapter.apply_policy.call_args.args[0]
    assert "m9-analytics.google-analytics.com" in applied_domains
    assert "microsoft.com" not in applied_domains

    verify_adapter = MagicMock()
    verify_adapter.available.return_value = True
    verify_adapter.verify.return_value = {
        "status": "verified",
        "provider": "adguard",
        "evidence": [{"domain": "m9-analytics.google-analytics.com", "blocked": True}],
    }
    with patch("api_verification.DNSBackendAdapter", return_value=verify_adapter):
        verification = client.get(f"/api/verification/policy/{pid}")
    assert verification.status_code == 200
    assert verification.json()["status"] == "verified"
    verify_adapter.verify.assert_called_once()

    rollback_adapter = MagicMock()
    rollback_adapter.available.return_value = True
    rollback_adapter.enabled = True
    rollback_adapter.restore_state.return_value = {
        "status": "restored",
        "provider": "adguard",
    }
    with patch("api_snapshot.DNSBackendAdapter", return_value=rollback_adapter):
        rolled_back = client.post(
            f"/api/snapshots/{snapshot_id}/rollback", params={"confirm": True}
        )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["status"] == "restored"
    rollback_adapter.restore_state.assert_called_once()
    assert client.get(f"/api/policies/{pid}").status_code == 200
    assert client.get(f"/api/policies/{pid}/execution").json()["status"] == "rolled_back"


def test_policy_apply_requires_approval():
    db = get_session_factory()()
    policy = Policy(
        name="Unapproved policy",
        action="block_domain_category",
        risk="Low",
        status="proposed",
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    pid = policy.id
    db.close()
    response = client.post(f"/api/policies/{pid}/apply")
    assert response.status_code == 400
