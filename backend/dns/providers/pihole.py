"""Pi-hole provider adapter.

The legacy ``collect`` method is preserved. Query retrieval uses the Pi-hole v6
JSON API when a URL and API token are configured; nothing is synthesized.
"""

from urllib.parse import urlsplit

import httpx

from dns.providers.adguard import normalize_domain, parse_provider_time
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


class PiHoleAdapter:
    def __init__(self, url=None, token=None, timeout=3.0, max_events=500):
        self.url = url.rstrip("/") if url else None
        self.token = token
        self.timeout = timeout
        self.max_events = max_events

    def available(self):
        return bool(self.url and urlsplit(self.url).scheme in {"http", "https"})

    def collect(self):
        return []

    def _get(self, path, params=None):
        if not self.available() or not self.token:
            raise ProviderNotConfigured("Pi-hole is not configured")
        try:
            response = httpx.get(
                f"{self.url}{path}",
                params=params,
                headers={"X-Pihole-Api-Token": self.token},
                timeout=self.timeout,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            raise ProviderTimeout("Pi-hole request timed out") from None
        except httpx.ConnectError:
            raise ProviderUnreachable("Pi-hole could not be reached") from None
        except httpx.HTTPError:
            raise ProviderUnavailable("Pi-hole request failed") from None
        if response.status_code in (401, 403):
            raise ProviderUnauthorized("Pi-hole rejected the API token")
        if response.status_code == 404:
            raise ProviderUnsupported("Pi-hole API endpoint is not available")
        if response.status_code >= 500:
            raise ProviderUnavailable("Pi-hole is temporarily unavailable")
        if response.status_code >= 400:
            raise ProviderUnavailable("Pi-hole rejected the request")
        try:
            return response.json()
        except ValueError:
            raise ProviderMalformedResponse("Pi-hole returned invalid JSON") from None

    def query_log(self, limit=100):
        body = self._get("/api/queries", params={"limit": max(1, min(int(limit), 500))})
        entries = None
        if isinstance(body, dict) and isinstance(body.get("queries"), list):
            entries = body["queries"]
        elif isinstance(body, list):
            entries = body
        if entries is None:
            raise ProviderMalformedResponse("Pi-hole query response is invalid")
        out = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            raw_domain = entry.get("domain")
            question = entry.get("question")
            if not raw_domain and isinstance(question, dict):
                raw_domain = question.get("name")
            domain = normalize_domain(raw_domain)
            if not domain:
                continue
            stamp = entry.get("timestamp")
            if isinstance(stamp, (int, float)):
                from datetime import datetime, timezone
                try:
                    stamp = datetime.fromtimestamp(float(stamp), timezone.utc)
                    stamp = stamp.replace(tzinfo=None)
                except (ValueError, OverflowError, OSError):
                    stamp = None
            else:
                stamp = parse_provider_time(stamp)
            if stamp is None:
                continue
            status = entry.get("status")
            blocked = None
            if isinstance(status, str):
                blocked = status.lower() in {"blocked", "blocked_gravity", "blocked_blacklist"}
            elif isinstance(status, int):
                blocked = status in (1, 2, 3, 4, 5)
            out.append(
                {
                    "domain": domain,
                    "query_type": None,
                    "client": str(entry.get("client")) if entry.get("client") else None,
                    "client_name": None,
                    "timestamp": stamp,
                    "status": str(status) if status is not None else None,
                    "reason": None,
                    "blocked": blocked,
                    "rules": [],
                    "upstream": None,
                    "source": "pihole",
                    "source_event_id": f"pihole-{int(stamp.timestamp())}-{domain}-{status}",
                }
            )
        return out

    def fetch_queries(self, max_events=None, page_size=None):
        limit = max_events if max_events is not None else self.max_events
        return self.query_log(limit=max(1, min(int(limit), 5000)))[:limit]

    def health(self):
        result = {
            "provider": "pihole",
            "endpoint_configured": self.available() and bool(self.token),
            "authentication": "configured" if self.token else "missing",
            "version": None,
            "state": "not_configured",
            "query_log": "unavailable",
            "statistics": "unavailable",
            "filtering": "unavailable",
            "capabilities": [],
            "unsupported": [],
        }
        if not result["endpoint_configured"]:
            return result
        try:
            records = self.query_log(limit=1)
        except ProviderError as error:
            result["state"] = error.state
            result["message"] = str(error)
            return result
        result["state"] = "healthy"
        result["query_log"] = "empty" if not records else "available"
        result["capabilities"] = ["api_connectivity", "authentication"]
        if records:
            result["capabilities"].append("query_log")
        else:
            result["unsupported"].append("query_log")
        result["statistics"] = "unsupported"
        result["filtering"] = "unsupported"
        result["unsupported"].extend(["statistics", "filtering"])
        return result
