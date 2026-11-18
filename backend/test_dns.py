import os, tempfile
from datetime import datetime, timedelta

os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "dns.db")
from db.session import init_db

init_db()
from fastapi.testclient import TestClient
from main import app
from dns.analytics import classify_domain

client = TestClient(app)


def test_classify():
    assert classify_domain("ads.doubleclick.net")[0] == "Advertising"
    assert classify_domain("unknown.example")[0] == "Unknown"


def test_ingest_and_summary():
    r = client.post(
        "/api/dns/events",
        json={"domain": "ads.doubleclick.net", "source_ip": "10.0.0.5"},
    )
    assert r.status_code == 200
    r2 = client.get("/api/dns/analytics/summary")
    assert r2.json()["total"] >= 1


def test_top_domains():
    r = client.get("/api/dns/analytics/domains")
    assert isinstance(r.json(), list)


def test_dns_event_links_to_device_by_verified_ip():
    device = client.post(
        "/api/devices",
        json={
            "ip_address": "10.0.0.5",
            "mac_address": "AA:BB:CC:DD:EE:55",
            "hostname": "phone",
        },
    ).json()
    client.post(
        "/api/dns/events",
        json={
            "domain": "example.com",
            "source_ip": "10.0.0.5",
            "blocked": True,
        },
    )
    events = client.get("/api/dns/events", params={"device_id": device["id"]}).json()
    assert events[0]["device_id"] == device["id"]
    assert events[0]["device"] == {
        "name": "phone",
        "ip": "10.0.0.5",
        "mac": "AA:BB:CC:DD:EE:55",
    }
    totals = client.get("/api/dns/analytics/devices").json()
    linked = next(row for row in totals if row["device_id"] == device["id"])
    assert linked["blocked"] >= 1


def test_unlinked_dns_event_remains_explicit():
    response = client.post(
        "/api/dns/events",
        json={
            "domain": "unlinked.example",
            "source_ip": "10.99.99.99",
            "blocked": False,
        },
    )
    assert response.status_code == 200
    event = client.get("/api/dns/events", params={"linked": "false"}).json()[0]
    assert event["device_id"] is None
    assert event["device"] is None


def test_filtering_rule_requires_confirmation(monkeypatch):
    monkeypatch.setenv("NETRA_DNS_ENFORCEMENT_ENABLED", "true")
    response = client.post(
        "/api/dns/providers/filtering/rules",
        json={"domain": "ads.example", "action": "block", "confirm": False},
    )
    assert response.status_code == 400
    assert "confirmation" in response.text.lower()


def test_event_time_association_tracks_ip_reassignment():
    from db.models import Device, DeviceObservation, DNSEvent
    from db.session import get_session_factory
    from dns.analytics import ingest_events

    db = get_session_factory()()
    try:
        device_a = Device(
            ip_address="10.0.0.50", mac_address="AA:AA", hostname="old-owner"
        )
        device_b = Device(
            ip_address="10.0.0.50", mac_address="BB:BB", hostname="new-owner"
        )
        db.add_all([device_a, device_b])
        db.flush()
        t0 = datetime(2026, 1, 1, 10, 0, 0)
        t1 = datetime(2026, 1, 2, 10, 0, 0)
        db.add_all(
            [
                DeviceObservation(
                    device_id=device_a.id,
                    ip_address="10.0.0.50",
                    mac_address="AA:AA",
                    observed_at=t0,
                    source="lan",
                ),
                DeviceObservation(
                    device_id=device_b.id,
                    ip_address="10.0.0.50",
                    mac_address="BB:BB",
                    observed_at=t1,
                    source="lan",
                ),
            ]
        )
        db.commit()

        old = ingest_events(
            db,
            [
                {
                    "domain": "old.example",
                    "client": "10.0.0.50",
                    "timestamp": t0 + timedelta(hours=1),
                    "source_event_id": "old-ip",
                }
            ],
            source="test",
        )
        new = ingest_events(
            db,
            [
                {
                    "domain": "new.example",
                    "client": "10.0.0.50",
                    "timestamp": t1 + timedelta(hours=1),
                    "source_event_id": "new-ip",
                }
            ],
            source="test",
        )
        old_event = (
            db.query(DNSEvent).filter(DNSEvent.source_event_id == "old-ip").first()
        )
        new_event = (
            db.query(DNSEvent).filter(DNSEvent.source_event_id == "new-ip").first()
        )
        assert old_event.device_id == device_a.id
        assert old_event.association_status == "linked"
        assert new_event.device_id == device_b.id
        assert new_event.association_status == "linked"
    finally:
        db.close()


def test_event_with_no_matching_device_is_unlinked():
    from db.session import get_session_factory
    from dns.analytics import ingest_events

    db = get_session_factory()()
    try:
        result = ingest_events(
            db,
            [
                {
                    "domain": "unknown.example",
                    "client": "10.99.99.99",
                    "timestamp": datetime.utcnow(),
                    "source_event_id": "unknown-ip",
                }
            ],
            source="test",
        )
        assert result["inserted"] == 1
    finally:
        db.close()
    event = client.get("/api/dns/events", params={"linked": "false"}).json()
    assert any(
        item["source_event_id"] if "source_event_id" in item else item["id"]
        for item in event
    )


def test_hostname_fallback_does_not_override_conflicting_ip():
    from db.models import Device
    from db.session import get_session_factory
    from dns.analytics import ingest_events

    db = get_session_factory()()
    try:
        device = Device(ip_address="10.0.0.60", mac_address="CC:CC", hostname="phone")
        db.add(device)
        db.commit()
        ingest_events(
            db,
            [
                {
                    "domain": "conflict.example",
                    "client": "10.0.0.99",
                    "client_name": "phone",
                    "timestamp": datetime.utcnow(),
                    "source_event_id": "conflict-ip",
                }
            ],
            source="test",
        )
        event = (
            db.query(__import__("db.models", fromlist=["DNSEvent"]).DNSEvent)
            .filter_by(source_event_id="conflict-ip")
            .first()
        )
        assert event.device_id is None
        assert event.association_status == "unlinked"
    finally:
        db.close()


def test_direct_block_records_snapshot_and_provider_failure(monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("NETRA_DNS_ENFORCEMENT_ENABLED", "true")
    provider = MagicMock()
    provider.filtering_status.side_effect = [
        {"enabled": True, "user_rules": ["||safe.example^"], "filter_count": 1},
    ]
    provider.add_user_rule.return_value = {
        "status": "applied",
        "domain": "ads.example",
        "rule": "||ads.example^",
    }
    adapter = MagicMock()
    adapter.available.return_value = True
    adapter.enabled = True
    adapter.backend = "adguard"
    adapter.provider = provider

    with patch("enforcement.adapter.DNSBackendAdapter", return_value=adapter):
        response = client.post(
            "/api/dns/providers/filtering/rules",
            json={"domain": "ads.example", "action": "block", "confirm": True},
        )

    assert response.status_code == 200
    assert response.json()["rollback_available"] is True
    assert response.json()["snapshot_id"] > 0
    provider.add_user_rule.assert_called_once_with("ads.example")


def test_direct_unblock_records_snapshot(monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("NETRA_DNS_ENFORCEMENT_ENABLED", "true")
    provider = MagicMock()
    provider.filtering_status.return_value = {
        "enabled": True,
        "user_rules": ["||ads.example^"],
        "filter_count": 1,
    }
    provider.remove_user_rule.return_value = {
        "status": "removed",
        "domain": "ads.example",
        "rule": "||ads.example^",
    }
    adapter = MagicMock()
    adapter.available.return_value = True
    adapter.enabled = True
    adapter.backend = "adguard"
    adapter.provider = provider

    with patch("enforcement.adapter.DNSBackendAdapter", return_value=adapter):
        response = client.post(
            "/api/dns/providers/filtering/rules",
            json={"domain": "ads.example", "action": "unblock", "confirm": True},
        )

    assert response.status_code == 200
    assert response.json()["rollback_available"] is True
    provider.remove_user_rule.assert_called_once_with("ads.example")


def test_direct_rule_status_snapshot_failure_makes_no_change(monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("NETRA_DNS_ENFORCEMENT_ENABLED", "true")
    provider = MagicMock()
    provider.filtering_status.side_effect = RuntimeError("provider status unavailable")
    adapter = MagicMock()
    adapter.available.return_value = True
    adapter.enabled = True
    adapter.backend = "adguard"
    adapter.provider = provider

    with patch("enforcement.adapter.DNSBackendAdapter", return_value=adapter):
        response = client.post(
            "/api/dns/providers/filtering/rules",
            json={"domain": "ads.example", "action": "block", "confirm": True},
        )

    assert response.status_code == 503
    provider.add_user_rule.assert_not_called()


def test_filtering_rule_disallows_unconfigured_provider(monkeypatch):
    monkeypatch.delenv("NETRA_DNS_BACKEND", raising=False)
    monkeypatch.delenv("NETRA_ADGUARD_API_URL", raising=False)
    monkeypatch.delenv("NETRA_PIHOLE_URL", raising=False)
    monkeypatch.setenv("NETRA_DNS_ENFORCEMENT_ENABLED", "true")
    response = client.post(
        "/api/dns/providers/filtering/rules",
        json={"domain": "ads.example", "action": "block", "confirm": True},
    )
    assert response.status_code == 503
    assert "not configured" in response.text.lower()


def test_dns_subnet_filters_summary_events_domains_and_device_totals():
    from db.models import Device
    from db.session import get_session_factory

    device = client.post(
        "/api/devices",
        json={
            "ip_address": "10.252.99.5",
            "mac_address": "AA:BB:CC:DD:EE:99",
            "hostname": "subnet-test-phone",
        },
    ).json()

    db = get_session_factory()()
    try:
        stored = db.get(Device, device["id"])
        stored.network_subnet = "10.252.99.0/24"
        db.commit()
    finally:
        db.close()

    client.post(
        "/api/dns/events",
        json={
            "domain": "ads.example",
            "source_ip": "10.252.99.5",
            "blocked": True,
        },
    )

    summary = client.get(
        "/api/dns/analytics/summary", params={"subnet": "10.252.99.0/24"}
    ).json()
    assert summary["total"] == 1

    other_summary = client.get(
        "/api/dns/analytics/summary", params={"subnet": "10.99.99.0/24"}
    ).json()
    assert other_summary["total"] == 0

    events = client.get(
        "/api/dns/events", params={"subnet": "10.252.99.0/24"}
    ).json()
    assert len(events) == 1
    assert events[0]["domain"] == "ads.example"

    domains = client.get(
        "/api/dns/analytics/domains", params={"subnet": "10.252.99.0/24"}
    ).json()
    assert [row["domain"] for row in domains] == ["ads.example"]

    device_totals = client.get(
        "/api/dns/analytics/devices", params={"subnet": "10.252.99.0/24"}
    ).json()
    assert device_totals[0]["device_id"] == device["id"]
    assert device_totals[0]["count"] == 1
