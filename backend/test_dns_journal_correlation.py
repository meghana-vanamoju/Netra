"""Tests for bounded dnsmasq journal correlation with AdGuard query records."""

import logging
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("NETRA_DB_PATH", os.path.join(tempfile.mkdtemp(), "dns-journal.db"))

from fastapi.testclient import TestClient

from db.models import DNSEvent
from db.session import get_session_factory, init_db
from dns.journal import (
    JournalConfig,
    _forwarded_candidates,
    correlate_events,
    parse_journal,
    read_forwarded_queries,
)
from main import app

init_db()
client = TestClient(app)

GATEWAY = "192.168.88.12"
HOTSPOT_CLIENT = "10.42.0.24"


def _record(domain="i.instagram.com", query_type="A", **overrides):
    record = {
        "domain": domain,
        "query_type": query_type,
        "client": GATEWAY,
        "client_name": None,
        "timestamp": datetime(2026, 11, 19, 10, 0, 0),
        "status": "NOERROR",
        "reason": "NotFilteredNotFound",
        "blocked": False,
        "rules": [],
        "upstream": "https://dns.example/dns-query",
        "source": "adguard-home",
        "source_event_id": "journal-event-1",
    }
    record.update(overrides)
    return record


def _epoch(timestamp):
    return timestamp.replace(tzinfo=timezone.utc).timestamp()


def _line(timestamp, message):
    return f"{timestamp:.6f} debian dnsmasq[126693]: {message}"


def _journal(timestamp, *, domain="i.instagram.com", query_type="A", client_ip=HOTSPOT_CLIENT, txid=1190):
    epoch = _epoch(timestamp)
    port = 53760
    return "\n".join(
        [
            _line(
                epoch,
                f"{txid} {client_ip}/{port} query[{query_type}] {domain} from {client_ip}",
            ),
            _line(
                epoch + 0.05,
                f"{txid} {client_ip}/{port} forwarded {domain} to {GATEWAY}",
            ),
        ]
    )


def _candidates(text):
    entries, _malformed = parse_journal(text)
    return _forwarded_candidates(entries)


def test_unique_forwarded_candidate_enriches_client_without_mutating_record():
    record = _record()
    original_client = record["client"]
    candidates = _candidates(_journal(record["timestamp"]))

    enriched, report = correlate_events([record], candidates, tolerance_seconds=2.0)

    assert report == {
        "candidates": 1,
        "enriched": 1,
        "already_matched": 0,
        "ambiguous": 0,
        "unmatched": 0,
    }
    assert enriched[0]["client"] == HOTSPOT_CLIENT
    assert record["client"] == original_client
    for key in (
        "source_event_id",
        "blocked",
        "reason",
        "rules",
        "upstream",
        "source",
        "status",
        "timestamp",
    ):
        assert enriched[0][key] == record[key]


def test_unique_candidate_with_already_matching_client_is_counted_separately():
    record = _record(client=HOTSPOT_CLIENT, upstream=GATEWAY)
    original = dict(record)
    candidates = _candidates(_journal(record["timestamp"]))

    enriched, report = correlate_events([record], candidates, tolerance_seconds=2.0)

    assert report == {
        "candidates": 1,
        "enriched": 0,
        "already_matched": 1,
        "ambiguous": 0,
        "unmatched": 0,
    }
    assert enriched == [record]
    assert enriched[0] is record
    assert enriched[0] == original


def test_domain_is_normalised_for_correlation():
    record = _record(domain="i.instagram.com")
    text = _journal(
        record["timestamp"],
        domain="I.Instagram.COM.",
    )
    candidates = _candidates(text)

    enriched, report = correlate_events([record], candidates, tolerance_seconds=2.0)

    assert report["enriched"] == 1
    assert enriched[0]["client"] == HOTSPOT_CLIENT


def test_query_type_mismatch_prevents_enrichment():
    record = _record(query_type="AAAA")
    candidates = _candidates(_journal(record["timestamp"], query_type="A"))

    enriched, report = correlate_events([record], candidates, tolerance_seconds=2.0)

    assert report["enriched"] == 0
    assert enriched[0]["client"] == GATEWAY


def test_timestamp_outside_tolerance_prevents_enrichment():
    record = _record()
    candidates = _candidates(_journal(record["timestamp"] + timedelta(seconds=10)))

    enriched, report = correlate_events([record], candidates, tolerance_seconds=2.0)

    assert report["enriched"] == 0
    assert enriched[0]["client"] == GATEWAY


def test_multiple_candidates_are_ambiguous_and_reported(caplog):
    record = _record()
    text = "\n".join(
        [
            _journal(record["timestamp"], client_ip="10.42.0.24", txid=1190),
            _journal(record["timestamp"], client_ip="10.42.0.25", txid=1191),
        ]
    )
    candidates = _candidates(text)
    caplog.set_level(logging.WARNING, logger="dns.journal")

    enriched, report = correlate_events([record], candidates, tolerance_seconds=2.0)

    assert len(candidates) == 2
    assert report["ambiguous"] == 1
    assert report["enriched"] == 0
    assert enriched[0]["client"] == GATEWAY
    assert "ambiguous" in caplog.text.lower()


def test_no_candidate_preserves_gateway_client():
    record = _record()

    enriched, report = correlate_events([record], [], tolerance_seconds=2.0)

    assert report["unmatched"] == 1
    assert enriched[0]["client"] == GATEWAY


def test_cached_and_reply_entries_are_ignored():
    timestamp = datetime(2026, 11, 19, 10, 0, 0)
    epoch = _epoch(timestamp)
    text = "\n".join(
        [
            _line(
                epoch,
                f"1190 {HOTSPOT_CLIENT}/53760 cached i.instagram.com is 1.2.3.4",
            ),
            _line(
                epoch,
                f"1190 {HOTSPOT_CLIENT}/53760 reply i.instagram.com is 1.2.3.4",
            ),
        ]
    )

    entries, malformed = parse_journal(text)

    assert malformed == 0
    assert all(entry.kind == "ignored" for entry in entries)
    assert _forwarded_candidates(entries) == ()


def test_malformed_journal_lines_are_skipped_safely():
    text = "\n".join(
        [
            "not a journal line",
            "1795066660.648662 debian dnsmasq[126693]: garbage",
            "1795066660.648662 debian dnsmasq[126693]: 1190 not-an-ip/53760 forwarded x to y",
            "1795066660.648662 debian dnsmasq[126693]: 1190 10.42.0.24/99999 forwarded x to y",
        ]
    )

    entries, malformed = parse_journal(text)

    assert entries == ()
    assert malformed == 4


def test_journal_command_failure_and_timeout_are_non_fatal():
    config = JournalConfig(timeout_seconds=1.0)
    failure = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
    with patch("dns.journal.subprocess.run", return_value=failure):
        failed = read_forwarded_queries(config)
    assert failed.state == "failed"
    assert failed.entries == ()

    timeout = subprocess.TimeoutExpired(cmd=["journalctl"], timeout=1.0)
    with patch("dns.journal.subprocess.run", side_effect=timeout):
        timed_out = read_forwarded_queries(config)
    assert timed_out.state == "timeout"
    assert timed_out.entries == ()


def test_journal_permission_failures_are_sanitised():
    config = JournalConfig()
    with patch("dns.journal.subprocess.run", side_effect=PermissionError("denied")):
        denied = read_forwarded_queries(config)
    assert denied.state == "permission_denied"

    rejected = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="Permission denied for journal"
    )
    with patch("dns.journal.subprocess.run", return_value=rejected):
        rejected_read = read_forwarded_queries(config)
    assert rejected_read.state == "permission_denied"


def test_disabled_correlation_requires_no_journal_access():
    with patch("dns.journal.subprocess.run") as runner:
        read = read_forwarded_queries(JournalConfig(enabled=False))
    assert read.state == "disabled"
    runner.assert_not_called()


def test_existing_blocked_status_and_filtering_metadata_survive_enrichment():
    record = _record(
        blocked=True,
        reason="FilteredBlackList",
        rules=["||i.instagram.com^"],
        upstream=None,
    )
    candidates = _candidates(_journal(record["timestamp"]))

    enriched, _report = correlate_events([record], candidates, tolerance_seconds=2.0)

    assert enriched[0]["blocked"] is True
    assert enriched[0]["reason"] == "FilteredBlackList"
    assert enriched[0]["rules"] == ["||i.instagram.com^"]
    assert enriched[0]["upstream"] is None
    assert enriched[0]["source_event_id"] == record["source_event_id"]


def test_journal_client_name_is_used_only_when_provider_name_is_absent():
    timestamp = datetime(2026, 11, 19, 10, 0, 0)
    epoch = _epoch(timestamp)
    text = "\n".join(
        [
            _line(
                epoch,
                f"1190 {HOTSPOT_CLIENT}/53760 query[A] i.instagram.com from phone",
            ),
            _line(
                epoch,
                f"1190 {HOTSPOT_CLIENT}/53760 forwarded i.instagram.com to {GATEWAY}",
            ),
        ]
    )
    candidates = _candidates(text)

    enriched, report = correlate_events(
        [_record(client_name=None)], candidates, tolerance_seconds=2.0
    )
    assert report["enriched"] == 1
    assert enriched[0]["client_name"] == "phone"

    provider_named = _record(client_name="gateway")
    preserved, _report = correlate_events(
        [provider_named], candidates, tolerance_seconds=2.0
    )
    assert preserved[0]["client_name"] == "gateway"


def _healthy_status():
    return {
        "provider": "adguard-home",
        "state": "healthy",
        "message": "Provider is reachable and responding.",
        "capabilities": ["api_connectivity", "authentication", "query_log"],
        "unsupported": [],
    }


def test_sync_enriches_once_and_remains_idempotent_with_mocked_journal():
    timestamp = datetime.utcnow().replace(microsecond=0)
    record = _record(
        domain="journal-sync-unique.example.com",
        timestamp=timestamp,
        blocked=True,
        reason="FilteredBlackList",
        rules=["||journal-sync-unique.example.com^"],
        upstream="https://dns.example/dns-query",
        source_event_id="journal-sync-1",
    )
    stdout = _journal(
        timestamp, domain="journal-sync-unique.example.com"
    ).replace("i.instagram.com", "journal-sync-unique.example.com")
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    with (
        patch("api_dns.provider_status", return_value=_healthy_status()),
        patch("api_dns.fetch_provider_queries", return_value=[record]),
        patch("dns.journal.subprocess.run", return_value=completed),
    ):
        first = client.post("/api/dns/events/sync")
        assert first.status_code == 200
        assert first.json()["inserted"] == 1
        assert first.json()["fetched"] == 1
        assert first.json()["correlation"]["candidates"] == 1
        assert first.json()["correlation"]["enriched"] == 1
        assert first.json()["correlation"]["already_matched"] == 0

        second = client.post("/api/dns/events/sync")
        assert second.status_code == 200
        assert second.json()["inserted"] == 0
        assert second.json()["duplicates"] == 1

    db = get_session_factory()()
    try:
        stored = (
            db.query(DNSEvent)
            .filter(DNSEvent.source_event_id == "journal-sync-1")
            .all()
        )
        assert len(stored) == 1
        assert stored[0].client == HOTSPOT_CLIENT
        assert stored[0].blocked == 1
        assert stored[0].reason == "FilteredBlackList"
        assert stored[0].rules_json == ["||journal-sync-unique.example.com^"]
        assert stored[0].upstream == "https://dns.example/dns-query"
    finally:
        db.close()


def test_sync_continues_with_original_provider_client_when_journal_fails():
    timestamp = datetime.utcnow().replace(microsecond=0)
    record = _record(
        domain="journal-failure-unique.example.com",
        timestamp=timestamp,
        source_event_id="journal-failure-1",
    )
    timeout = subprocess.TimeoutExpired(cmd=["journalctl"], timeout=2.0)

    with (
        patch("api_dns.provider_status", return_value=_healthy_status()),
        patch("api_dns.fetch_provider_queries", return_value=[record]),
        patch("dns.journal.subprocess.run", side_effect=timeout),
    ):
        response = client.post("/api/dns/events/sync")

    assert response.status_code == 200
    assert response.json()["inserted"] == 1
    assert response.json()["state"] == "healthy"

    db = get_session_factory()()
    try:
        stored = (
            db.query(DNSEvent)
            .filter(DNSEvent.source_event_id == "journal-failure-1")
            .one()
        )
        assert stored.client == GATEWAY
    finally:
        db.close()


def test_sync_reports_ambiguity_and_keeps_provider_client():
    timestamp = datetime.utcnow().replace(microsecond=0)
    domain = "journal-ambiguous-unique.example.com"
    record = _record(
        domain=domain,
        timestamp=timestamp,
        source_event_id="journal-ambiguous-1",
    )
    stdout = "\n".join(
        [
            _journal(timestamp, domain=domain, client_ip="10.42.0.24", txid=1200),
            _journal(timestamp, domain=domain, client_ip="10.42.0.25", txid=1201),
        ]
    )
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    with (
        patch("api_dns.provider_status", return_value=_healthy_status()),
        patch("api_dns.fetch_provider_queries", return_value=[record]),
        patch("dns.journal.subprocess.run", return_value=completed),
    ):
        response = client.post("/api/dns/events/sync")

    assert response.status_code == 200
    assert response.json()["correlation"]["candidates"] == 2
    assert response.json()["correlation"]["ambiguous"] == 1
    assert response.json()["correlation"]["enriched"] == 0
    assert response.json()["correlation"]["already_matched"] == 0

    db = get_session_factory()()
    try:
        stored = (
            db.query(DNSEvent)
            .filter(DNSEvent.source_event_id == "journal-ambiguous-1")
            .one()
        )
        assert stored.client == GATEWAY
    finally:
        db.close()
