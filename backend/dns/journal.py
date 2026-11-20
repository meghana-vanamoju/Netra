"""Conservative dnsmasq journal correlation for AdGuard query events.

NetworkManager's dnsmasq logs the original hotspot client on ``forwarded``
lines. AdGuard Home, however, can record the gateway address as the client.
This module reads those journal lines without sudo and enriches only the
original client IP (and a client name only when the journal supplies one).

The reader is deliberately bounded and best-effort. Any journal access or
parsing failure leaves provider records untouched so an existing sync remains
functional. A dnsmasq ``0.0.0.0`` answer is never interpreted as an AdGuard
block; filtering status remains authoritative in the provider record.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from dns.providers.adguard import normalize_domain

LOGGER = logging.getLogger(__name__)

DEFAULT_TOLERANCE_SECONDS = 2.0
DEFAULT_WINDOW_SECONDS = 300
DEFAULT_MAX_LINES = 2000
DEFAULT_TIMEOUT_SECONDS = 2.0
DEFAULT_UNIT = "NetworkManager"

_JOURNAL_PREFIX_RE = re.compile(
    r"^(?P<epoch>\d+(?:\.\d+)?)\s+(?:\S+\s+)?dnsmasq(?:\[\d+\])?:\s*(?P<message>.*)$"
)
_TRANSACTION_RE = re.compile(
    r"^(?P<txid>\d+)\s+(?P<client>[0-9A-Fa-f:.]+)/(?P<port>\d+)\s+(?P<rest>.*)$"
)
_FORWARDED_RE = re.compile(
    r"^forwarded\s+(?P<domain>\S+)\s+to\s+(?P<upstream>\S+)\s*$", re.IGNORECASE
)
_QUERY_RE = re.compile(
    r"^query\[(?P<qtype>[A-Z0-9_-]+)\]\s+(?P<domain>\S+)"
    r"(?:\s+from\s+(?P<source>\S+))?\s*$",
    re.IGNORECASE,
)
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
_IGNORED_RE = re.compile(r"^(?:cached|reply)\b", re.IGNORECASE)

_PERMISSION_MARKERS = (
    "permission denied",
    "access denied",
    "not authorized",
    "operation not permitted",
)


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _env_float(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high else default


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high else default


@dataclass(frozen=True)
class JournalConfig:
    """Bounded journal access settings, all overridable by environment."""

    enabled: bool = True
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS
    window_seconds: int = DEFAULT_WINDOW_SECONDS
    max_lines: int = DEFAULT_MAX_LINES
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    unit: str = DEFAULT_UNIT

    @classmethod
    def from_env(cls) -> "JournalConfig":
        return cls(
            enabled=_env_flag("NETRA_DNSMASQ_CORRELATION_ENABLED", True),
            tolerance_seconds=_env_float(
                "NETRA_DNSMASQ_CORRELATION_TOLERANCE_SECONDS",
                DEFAULT_TOLERANCE_SECONDS,
                0.1,
                60.0,
            ),
            window_seconds=_env_int(
                "NETRA_DNSMASQ_JOURNAL_WINDOW_SECONDS",
                DEFAULT_WINDOW_SECONDS,
                30,
                3600,
            ),
            max_lines=_env_int(
                "NETRA_DNSMASQ_JOURNAL_MAX_LINES", DEFAULT_MAX_LINES, 100, 20000
            ),
            timeout_seconds=_env_float(
                "NETRA_DNSMASQ_JOURNAL_TIMEOUT_SECONDS",
                DEFAULT_TIMEOUT_SECONDS,
                0.1,
                30.0,
            ),
            unit=(os.environ.get("NETRA_DNSMASQ_JOURNAL_UNIT") or DEFAULT_UNIT).strip()
            or DEFAULT_UNIT,
        )

    @property
    def command(self) -> list[str]:
        return [
            "journalctl",
            "--unit",
            self.unit,
            "--since",
            f"-{self.window_seconds}s",
            "--lines",
            str(self.max_lines),
            "--no-pager",
            "--output=short-unix",
        ]


@dataclass(frozen=True)
class DnsmasqEntry:
    timestamp: datetime
    kind: str
    transaction_id: str
    client_ip: str
    source_port: str
    domain: str | None = None
    query_type: str | None = None
    forwarded_to: str | None = None
    client_name: str | None = None


@dataclass(frozen=True)
class JournalRead:
    state: str
    entries: tuple[DnsmasqEntry, ...] = ()
    detail: str | None = None


def _parse_epoch(value: str) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _valid_client_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _normalise_endpoint(value: object) -> str | None:
    """Normalise an AdGuard client/upstream or dnsmasq forward target."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if "://" in candidate:
        candidate = candidate.split("://", 1)[1]
    candidate = candidate.split("/", 1)[0]
    if candidate.startswith("[") and "]" in candidate:
        candidate = candidate[1:].split("]", 1)[0]
    elif "#" in candidate:
        candidate = candidate.split("#", 1)[0]
    if "#" in candidate:
        candidate = candidate.split("#", 1)[0]
    valid_ip = _valid_client_ip(candidate)
    if valid_ip:
        return valid_ip
    candidate = candidate.rstrip(".").lower()
    return candidate if _HOSTNAME_RE.match(candidate) else None


def _client_name_from_source(source: str | None, client_ip: str) -> str | None:
    if not source or _valid_client_ip(source):
        return None
    candidate = source.strip().rstrip(".").lower()
    if not _HOSTNAME_RE.match(candidate) or candidate == client_ip:
        return None
    return candidate


def parse_journal_line(line: str) -> DnsmasqEntry | None:
    """Parse one ``short-unix`` journal line; return None when unusable."""
    prefix = _JOURNAL_PREFIX_RE.match(line.strip())
    if not prefix:
        return None
    timestamp = _parse_epoch(prefix.group("epoch"))
    if timestamp is None:
        return None
    transaction = _TRANSACTION_RE.match(prefix.group("message").strip())
    if not transaction:
        return None
    client_ip = _valid_client_ip(transaction.group("client"))
    port = int(transaction.group("port"))
    if client_ip is None or not 1 <= port <= 65535:
        return None
    rest = transaction.group("rest").strip()

    forwarded = _FORWARDED_RE.match(rest)
    if forwarded:
        domain = normalize_domain(forwarded.group("domain"))
        upstream = _normalise_endpoint(forwarded.group("upstream"))
        if not domain or not upstream:
            return None
        return DnsmasqEntry(
            timestamp=timestamp,
            kind="forwarded",
            transaction_id=transaction.group("txid"),
            client_ip=client_ip,
            source_port=str(port),
            domain=domain,
            forwarded_to=upstream,
        )

    query = _QUERY_RE.match(rest)
    if query:
        domain = normalize_domain(query.group("domain"))
        if not domain:
            return None
        return DnsmasqEntry(
            timestamp=timestamp,
            kind="query",
            transaction_id=transaction.group("txid"),
            client_ip=client_ip,
            source_port=str(port),
            domain=domain,
            query_type=query.group("qtype").upper(),
            client_name=_client_name_from_source(query.group("source"), client_ip),
        )

    # Cached and reply entries are valid journal messages but never upstream
    # requests. Keep them visible to parsers without creating candidates.
    if _IGNORED_RE.match(rest):
        return DnsmasqEntry(
            timestamp=timestamp,
            kind="ignored",
            transaction_id=transaction.group("txid"),
            client_ip=client_ip,
            source_port=str(port),
        )
    return None


def parse_journal(text: str) -> tuple[tuple[DnsmasqEntry, ...], int]:
    """Parse journal output into entries plus a malformed-line count."""
    entries: list[DnsmasqEntry] = []
    malformed = 0
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        entry = parse_journal_line(line)
        if entry is None:
            malformed += 1
        else:
            entries.append(entry)
    return tuple(entries), malformed


def _forwarded_candidates(entries: Iterable[DnsmasqEntry]) -> tuple[DnsmasqEntry, ...]:
    """Attach query metadata and return unique, usable forwarded entries."""
    types: dict[tuple[str, str, str, str], set[str]] = {}
    names: dict[tuple[str, str, str, str], set[str]] = {}
    for entry in entries:
        if entry.kind != "query" or not entry.domain:
            continue
        key = (
            entry.transaction_id,
            entry.client_ip,
            entry.source_port,
            entry.domain,
        )
        if entry.query_type:
            types.setdefault(key, set()).add(entry.query_type)
        if entry.client_name:
            names.setdefault(key, set()).add(entry.client_name)

    candidates: dict[tuple[object, ...], DnsmasqEntry] = {}
    for entry in entries:
        if entry.kind != "forwarded" or not entry.domain or not entry.forwarded_to:
            continue
        key = (
            entry.transaction_id,
            entry.client_ip,
            entry.source_port,
            entry.domain,
        )
        query_types = types.get(key, set())
        query_type = next(iter(query_types)) if len(query_types) == 1 else None
        client_names = names.get(key, set())
        client_name = next(iter(client_names)) if len(client_names) == 1 else None
        candidate = DnsmasqEntry(
            timestamp=entry.timestamp,
            kind=entry.kind,
            transaction_id=entry.transaction_id,
            client_ip=entry.client_ip,
            source_port=entry.source_port,
            domain=entry.domain,
            query_type=query_type,
            forwarded_to=entry.forwarded_to,
            client_name=client_name,
        )
        fingerprint = (
            candidate.timestamp,
            candidate.transaction_id,
            candidate.client_ip,
            candidate.source_port,
            candidate.domain,
            candidate.query_type,
            candidate.forwarded_to,
            candidate.client_name,
        )
        candidates.setdefault(fingerprint, candidate)
    return tuple(candidates.values())


def read_forwarded_queries(config: JournalConfig | None = None) -> JournalRead:
    """Read bounded NetworkManager journal output without elevated privileges."""
    cfg = config or JournalConfig.from_env()
    if not cfg.enabled:
        return JournalRead(state="disabled")
    try:
        completed = subprocess.run(
            cfg.command,
            capture_output=True,
            text=True,
            timeout=cfg.timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return JournalRead(state="unavailable", detail="journalctl is not installed")
    except subprocess.TimeoutExpired:
        return JournalRead(state="timeout", detail="journalctl timed out")
    except PermissionError:
        return JournalRead(state="permission_denied", detail="journal access denied")
    except OSError as error:
        return JournalRead(state="unavailable", detail=type(error).__name__)

    if completed.returncode != 0:
        stderr = (completed.stderr or "").lower()
        state = (
            "permission_denied"
            if any(marker in stderr for marker in _PERMISSION_MARKERS)
            else "failed"
        )
        return JournalRead(state=state, detail=f"journalctl exit {completed.returncode}")

    entries, malformed = parse_journal(completed.stdout or "")
    if malformed:
        LOGGER.debug("Ignored %d malformed dnsmasq journal lines", malformed)
    return JournalRead(state="ok", entries=_forwarded_candidates(entries))


def _record_time(record: dict) -> datetime | None:
    timestamp = record.get("timestamp")
    if isinstance(timestamp, datetime):
        return timestamp.astimezone(timezone.utc).replace(tzinfo=None) if timestamp.tzinfo else timestamp
    return None


def _upstream_matches(record: dict, candidate: DnsmasqEntry) -> bool:
    """Require the forward target to be the provider client or upstream."""
    known = {
        normalised
        for value in (record.get("client"), record.get("upstream"))
        if (normalised := _normalise_endpoint(value)) is not None
    }
    return bool(known) and candidate.forwarded_to in known


def correlate_events(
    records: Iterable[dict],
    candidates: Iterable[DnsmasqEntry],
    tolerance_seconds: float | None = None,
) -> tuple[list[dict], dict]:
    """Return records with conservative, unique-only client enrichment.

    The report counts ``enriched``, ``already_matched``, ``ambiguous`` and
    ``unmatched`` outcomes; only enriched records are copied and changed.
    """
    tolerance = (
        JournalConfig.from_env().tolerance_seconds
        if tolerance_seconds is None
        else tolerance_seconds
    )
    candidates = tuple(candidates)
    enriched_records: list[dict] = []
    report = {
        "candidates": len(candidates),
        "enriched": 0,
        "already_matched": 0,
        "ambiguous": 0,
        "unmatched": 0,
    }

    for record in records:
        if not isinstance(record, dict):
            enriched_records.append(record)
            report["unmatched"] += 1
            continue
        domain = normalize_domain(record.get("domain"))
        query_type = record.get("query_type")
        query_type = query_type.strip().upper() if isinstance(query_type, str) else None
        timestamp = _record_time(record)
        matches: list[DnsmasqEntry] = []
        if domain and query_type and timestamp is not None:
            for candidate in candidates:
                if candidate.domain != domain or candidate.query_type != query_type:
                    continue
                if abs((candidate.timestamp - timestamp).total_seconds()) > tolerance:
                    continue
                if not _upstream_matches(record, candidate):
                    continue
                matches.append(candidate)

        if len(matches) == 1:
            candidate = matches[0]
            client = str(record.get("client") or "").strip() or None
            if candidate.client_ip and candidate.client_ip != client:
                enriched = dict(record)
                enriched["client"] = candidate.client_ip
                if not record.get("client_name") and candidate.client_name:
                    enriched["client_name"] = candidate.client_name
                enriched_records.append(enriched)
                report["enriched"] += 1
                continue
            if candidate.client_ip and candidate.client_ip == client:
                report["already_matched"] += 1
        elif len(matches) > 1:
            report["ambiguous"] += 1
            LOGGER.warning(
                "dnsmasq correlation ambiguous for %s %s: %d candidates",
                domain,
                query_type,
                len(matches),
            )
        else:
            report["unmatched"] += 1
        enriched_records.append(record)

    return enriched_records, report


def enrich_from_journal(
    records: Iterable[dict], config: JournalConfig | None = None
) -> tuple[list[dict], dict]:
    """Apply journal enrichment; any journal failure is non-fatal."""
    cfg = config or JournalConfig.from_env()
    source_records = list(records)
    read = read_forwarded_queries(cfg)
    report = {
        "journal": read.state,
        "candidates": 0,
        "enriched": 0,
        "already_matched": 0,
        "ambiguous": 0,
        "unmatched": 0,
    }
    if read.state != "ok":
        if read.state != "disabled":
            LOGGER.info(
                "dnsmasq correlation unavailable (%s); using provider clients",
                read.state,
            )
        return source_records, report

    enriched, correlation = correlate_events(
        source_records, read.entries, cfg.tolerance_seconds
    )
    report.update(correlation)
    if report["ambiguous"]:
        LOGGER.warning(
            "dnsmasq correlation left %d provider event(s) unmodified as ambiguous",
            report["ambiguous"],
        )
    return enriched, report
