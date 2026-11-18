import hashlib
import ipaddress
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from dns.providers.errors import (
    ProviderError,
    ProviderMalformedResponse,
    ProviderNotConfigured,
    ProviderTimeout,
    ProviderUnauthorized,
    ProviderUnavailable,
    ProviderUnreachable,
    ProviderUnsupported,
)

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)


def normalize_domain(value: object) -> str | None:
    """Lowercase, strip a trailing dot, and validate a DNS domain name."""
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower().rstrip(".")
    if not candidate or not DOMAIN_RE.match(candidate):
        return None
    return candidate


def parse_provider_time(value: object) -> datetime | None:
    """Parse AdGuard Home RFC3339 timestamps (which may carry nanoseconds)."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        match = re.match(r"^(.*?\.\d{6})\d*([+-]\d{2}:\d{2})$", text)
        if match:
            text = match.group(1) + match.group(2)
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None


class AdGuardHomeAdapter:
    """Read-mostly AdGuard Home adapter.

    ``dhcp_status``/``collect`` retain their original router-inventory behavior.
    Query-log, statistics and filtering methods support the DNS monitoring
    milestone. No credential is ever included in a result or error message.
    """

    def __init__(
        self,
        url=None,
        username=None,
        password=None,
        timeout=3.0,
        connect_timeout=None,
        page_size=100,
        max_events=500,
    ):
        self.url = url.rstrip("/") if url else None
        self.username = username
        self.password = password
        self.timeout = timeout
        self.connect_timeout = connect_timeout or timeout
        self.page_size = page_size
        self.max_events = max_events

    def available(self):
        return bool(self.url and urlsplit(self.url).scheme in {"http", "https"})

    def _auth(self):
        return (
            (self.username, self.password)
            if self.username and self.password
            else None
        )

    def _timeout(self):
        try:
            return httpx.Timeout(
                float(self.timeout), connect=float(self.connect_timeout)
            )
        except (TypeError, ValueError):
            return httpx.Timeout(3.0, connect=3.0)

    def _translate_http_error(self, error: httpx.HTTPError) -> ProviderError:
        if isinstance(error, httpx.TimeoutException):
            return ProviderTimeout("AdGuard Home request timed out")
        if isinstance(error, httpx.ConnectError):
            return ProviderUnreachable("AdGuard Home could not be reached")
        return ProviderUnavailable("AdGuard Home request failed")

    def _get_json(self, path, params=None):
        if not self.available():
            raise ProviderNotConfigured("AdGuard Home is not configured")
        try:
            response = httpx.get(
                f"{self.url}{path}",
                params=params,
                auth=self._auth(),
                timeout=self._timeout(),
                follow_redirects=False,
            )
        except httpx.HTTPError as error:
            raise self._translate_http_error(error) from None
        return self._response_json(response)

    def _post_json(self, path, payload):
        if not self.available():
            raise ProviderNotConfigured("AdGuard Home is not configured")
        try:
            response = httpx.post(
                f"{self.url}{path}",
                json=payload,
                auth=self._auth(),
                timeout=self._timeout(),
                follow_redirects=False,
            )
        except httpx.HTTPError as error:
            raise self._translate_http_error(error) from None
        return self._response_json(response, allow_empty=True)

    @staticmethod
    def _response_json(response, allow_empty=False):
        status = response.status_code
        if status in (401, 403):
            raise ProviderUnauthorized("AdGuard Home rejected the credentials")
        if status == 404:
            raise ProviderUnsupported("AdGuard Home API endpoint is not available")
        if status >= 500:
            raise ProviderUnavailable("AdGuard Home is temporarily unavailable")
        if status >= 400:
            raise ProviderUnavailable("AdGuard Home rejected the request")
        if allow_empty and getattr(response, "content", b"x") == b"":
            return {}
        try:
            return response.json()
        except ValueError:
            raise ProviderMalformedResponse(
                "AdGuard Home returned invalid JSON"
            ) from None

    # ---- existing router-inventory API (unchanged behavior) ----------------

    def dhcp_status(self):
        if not self.available():
            raise RuntimeError("AdGuard Home is not configured")
        auth = self._auth()
        response = httpx.get(
            f"{self.url}/control/dhcp/status",
            auth=auth,
            timeout=self.timeout,
            follow_redirects=False,
        )
        response.raise_for_status()
        return response.json()

    def collect(self):
        status = self.dhcp_status()
        if not isinstance(status, dict):
            raise ValueError("Invalid AdGuard Home DHCP response")
        devices = []
        for lease_type, key in (("dhcp", "leases"), ("static", "static_leases")):
            leases = status.get(key, [])
            if not isinstance(leases, list):
                raise ValueError("Invalid AdGuard Home DHCP lease list")
            for lease in leases:
                if not isinstance(lease, dict):
                    continue
                ip_address = lease.get("ip")
                if not isinstance(ip_address, str):
                    continue
                try:
                    ip_address = str(ipaddress.ip_address(ip_address))
                except ValueError:
                    continue
                mac_address = lease.get("mac")
                hostname = lease.get("hostname")
                expires = lease.get("expires")
                devices.append(
                    {
                        "ip_address": ip_address,
                        "mac_address": mac_address.strip().upper()
                        if isinstance(mac_address, str) and mac_address.strip()
                        else None,
                        "hostname": hostname
                        if isinstance(hostname, str) and hostname
                        else None,
                        "vendor": None,
                        "connection_type": lease_type,
                        "online_status": "unknown",
                        "lease_expires": expires
                        if isinstance(expires, str) and expires
                        else None,
                        "last_seen": None,
                        "discovery_source": "router:adguard-home",
                    }
                )
        return devices

    # ---- DNS monitoring API ------------------------------------------------

    def query_log(self, limit=100, offset=0):
        """Return normalized query records from ``/control/querylog``."""
        body = self._get_json(
            "/control/querylog",
            params={"limit": max(1, min(int(limit), 500)), "offset": max(0, int(offset))},
        )
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise ProviderMalformedResponse("AdGuard Home query-log response is invalid")
        records = []
        for entry in body["data"]:
            record = self._normalize_query(entry)
            if record:
                records.append(record)
        return records

    @staticmethod
    def _normalize_query(entry):
        if not isinstance(entry, dict):
            return None
        question = entry.get("question")
        if not isinstance(question, dict):
            return None
        domain = normalize_domain(question.get("name"))
        if not domain:
            return None
        query_type = question.get("type")
        query_type = query_type.upper() if isinstance(query_type, str) else None
        client = entry.get("client")
        client = client.strip() if isinstance(client, str) and client.strip() else None
        client_info = entry.get("client_info")
        client_name = None
        if isinstance(client_info, dict) and isinstance(client_info.get("name"), str):
            client_name = client_info["name"].strip() or None
        reason = entry.get("reason")
        reason = reason if isinstance(reason, str) and reason else None
        status = entry.get("status")
        status = status if isinstance(status, str) and status else None
        rules = entry.get("rules")
        rules = [str(r) for r in rules if isinstance(r, str) and r] if isinstance(rules, list) else []
        upstream = entry.get("upstream")
        upstream = upstream if isinstance(upstream, str) and upstream else None
        timestamp = parse_provider_time(entry.get("time"))
        if timestamp is None:
            return None
        blocked = None
        if reason:
            blocked = reason.startswith("Filtered") or reason.startswith("Blocked")
        fingerprint = "|".join(
            [timestamp.isoformat(), domain, query_type or "", client or "", reason or ""]
        )
        return {
            "domain": domain,
            "query_type": query_type,
            "client": client,
            "client_name": client_name,
            "timestamp": timestamp,
            "status": status,
            "reason": reason,
            "blocked": blocked,
            "rules": rules,
            "upstream": upstream,
            "source": "adguard-home",
            "source_event_id": hashlib.sha256(fingerprint.encode()).hexdigest()[:32],
        }

    def fetch_queries(self, max_events=None, page_size=None):
        """Bounded, deduplicated newest-first retrieval."""
        limit = max_events if max_events is not None else self.max_events
        page = page_size if page_size is not None else self.page_size
        limit = max(1, min(int(limit), 5000))
        page = max(1, min(int(page), 500))
        seen = set()
        out = []
        offset = 0
        while len(out) < limit:
            batch = self.query_log(limit=min(page, limit - len(out)), offset=offset)
            if not batch:
                break
            new = 0
            for item in batch:
                key = item["source_event_id"]
                if key in seen:
                    continue
                seen.add(key)
                out.append(item)
                new += 1
                if len(out) >= limit:
                    break
            offset += len(batch)
            if new == 0:
                break
        return out

    def statistics(self):
        body = self._get_json("/control/stats")
        if not isinstance(body, dict):
            raise ProviderMalformedResponse("AdGuard Home statistics response is invalid")
        return {
            "total_queries": body.get("num_dns_queries")
            if isinstance(body.get("num_dns_queries"), int)
            else None,
            "blocked_queries": body.get("num_blocked_filtering")
            if isinstance(body.get("num_blocked_filtering"), int)
            else None,
            "top_queried_domains": body.get("top_queried_domains")
            if isinstance(body.get("top_queried_domains"), list)
            else [],
            "top_blocked_domains": body.get("top_blocked_domains")
            if isinstance(body.get("top_blocked_domains"), list)
            else [],
            "top_clients": body.get("top_clients")
            if isinstance(body.get("top_clients"), list)
            else [],
        }

    def filtering_status(self):
        body = self._get_json("/control/filtering/status")
        if not isinstance(body, dict):
            raise ProviderMalformedResponse("AdGuard Home filtering response is invalid")
        rules = body.get("user_rules")
        return {
            "enabled": bool(body.get("enabled")),
            "user_rules": [str(r) for r in rules if isinstance(r, str)] if isinstance(rules, list) else [],
            "filter_count": len(body.get("filters", []))
            if isinstance(body.get("filters"), list)
            else None,
        }

    def health(self):
        """Return sanitized connectivity/authentication/capability state."""
        result = {
            "provider": "adguard-home",
            "endpoint_configured": self.available(),
            "authentication": "not_required"
            if not (self.username and self.password)
            else "configured",
            "version": None,
            "state": "not_configured",
            "query_log": "unavailable",
            "statistics": "unavailable",
            "filtering": "unavailable",
            "capabilities": [],
            "unsupported": [],
        }
        if not self.available():
            return result
        try:
            status = self._get_json("/control/status")
            if not isinstance(status, dict):
                raise ProviderMalformedResponse("AdGuard Home status response is invalid")
        except ProviderError as error:
            result["state"] = error.state
            if error.state == "unauthorized":
                result["authentication"] = "failed"
            result["message"] = str(error)
            return result
        result["state"] = "healthy"
        result["version"] = status.get("version") if isinstance(status.get("version"), str) else None
        result["capabilities"].extend(["api_connectivity", "authentication"])
        if status.get("protection_enabled") is True:
            result["capabilities"].append("protection_enabled")
        for name, checker in (
            ("query_log", self._probe_query_log),
            ("statistics", self._probe_statistics),
            ("filtering", self._probe_filtering),
        ):
            result[name] = checker()
            if result[name] in ("available", "empty"):
                result["capabilities"].append(name)
            else:
                result["unsupported"].append(name)
        return result

    def _probe_query_log(self):
        try:
            return "empty" if not self.query_log(limit=1) else "available"
        except ProviderUnsupported:
            return "unsupported"
        except ProviderError:
            return "unavailable"

    def _probe_statistics(self):
        try:
            return "available" if isinstance(self._get_json("/control/stats"), dict) else "malformed"
        except ProviderUnsupported:
            return "unsupported"
        except ProviderError:
            return "unavailable"

    def _probe_filtering(self):
        try:
            return "available" if isinstance(self._get_json("/control/filtering/status"), dict) else "malformed"
        except ProviderUnsupported:
            return "unsupported"
        except ProviderError:
            return "unavailable"

    # ---- controlled, explicitly-enabled enforcement helpers ---------------

    @staticmethod
    def user_rule(domain: str, action: str = "block") -> str:
        domain = normalize_domain(domain)
        if not domain:
            raise ValueError("Invalid domain for a filtering rule")
        if action == "allow":
            return f"@@||{domain}^"
        if action in ("block", "unblock", "remove"):
            return f"||{domain}^"
        raise ValueError("Unsupported filtering rule action")

    def add_user_rule(self, domain: str, action: str = "block") -> dict:
        rule = self.user_rule(domain, "allow" if action == "allow" else "block")
        current = self.filtering_status()
        rules = current["user_rules"]
        if rule not in rules:
            rules = rules + [rule]
            self._post_json("/control/filtering/set_rules", {"rules": rules})
        return {
            "provider": "adguard-home",
            "domain": normalize_domain(domain),
            "rule": rule,
            "action": "allow" if action == "allow" else "block",
            "status": "applied",
        }

    def remove_user_rule(self, domain: str, action: str | None = None) -> dict:
        normalized = normalize_domain(domain)
        if not normalized:
            raise ValueError("Invalid domain for a filtering rule")
        if action == "allow":
            removable = {self.user_rule(normalized, "allow")}
        elif action in (None, "unblock", "remove"):
            removable = {
                self.user_rule(normalized, "block"),
                self.user_rule(normalized, "allow"),
            }
        else:
            raise ValueError("Unsupported filtering rule action")
        current = self.filtering_status()
        rules = [r for r in current["user_rules"] if r not in removable]
        self._post_json("/control/filtering/set_rules", {"rules": rules})
        return {
            "provider": "adguard-home",
            "domain": normalized,
            "rules": sorted(removable),
            "status": "removed",
        }

    def refresh_filters(self) -> dict:
        """Ask AdGuard to refresh configured filter lists; no router change."""
        self._post_json("/control/filtering/refresh", {})
        return {"provider": "adguard-home", "status": "refreshed"}

    def restore_user_rules(self, rules) -> dict:
        """Restore an exact, previously snapshotted user-rule list."""
        if not isinstance(rules, list):
            raise ValueError("Invalid user-rule snapshot")
        clean = []
        for rule in rules:
            if not isinstance(rule, str) or len(rule) > 255 or "\n" in rule:
                raise ValueError("Invalid user-rule snapshot")
            clean.append(rule)
        self._post_json("/control/filtering/set_rules", {"rules": clean})
        return {"provider": "adguard-home", "status": "restored", "rules": len(clean)}

    def blocked_evidence(self, domain: str, limit: int = 100) -> dict:
        domain = normalize_domain(domain)
        if not domain:
            return {"domain": domain, "blocked": False, "evidence": "invalid domain"}
        try:
            records = self.query_log(limit=limit)
        except ProviderError as error:
            return {"domain": domain, "blocked": False, "evidence": error.state}
        matches = [r for r in records if r["domain"] == domain]
        for record in matches:
            if record["blocked"]:
                return {
                    "domain": domain,
                    "blocked": True,
                    "evidence": record["reason"],
                    "observed_at": record["timestamp"].isoformat(),
                }
        return {
            "domain": domain,
            "blocked": False,
            "evidence": "no filtered query observed in the retrieved log",
            "matches": len(matches),
        }
