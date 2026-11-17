"""Opt-in DNS enforcement adapter.

Nothing here is called automatically: API routes require explicit user consent
and a separately enabled enforcement flag. All results are credential-free.
"""

import os

from dns.providers.adguard import normalize_domain
from dns.providers.config import ProviderConfig
from dns.providers.errors import ProviderError, STATE_MESSAGES
from dns.providers.registry import get_provider, resolve_config


class DNSBackendAdapter:
    def __init__(self, config=None):
        self.config = resolve_config(config)
        self.backend = self.config.backend or (
            "adguard" if self.config.adguard_configured else
            "pihole" if self.config.pihole_configured else None
        )
        self.provider = get_provider(self.config)

    def available(self):
        return bool(self.provider)

    @property
    def enabled(self):
        return self.config.enforcement_enabled

    def _domains(self, domains):
        out = []
        for value in domains or []:
            domain = normalize_domain(value)
            if domain and domain not in out:
                out.append(domain)
        return out

    def apply_policy(self, domains):
        targets = self._domains(domains)
        if not targets:
            return {"status": "invalid", "reason": "No valid target domains"}
        if not self.available():
            return {"status": "unavailable", "reason": "No configured DNS provider"}
        if not self.enabled:
            return {
                "status": "enforcement_disabled",
                "reason": "NETRA_DNS_ENFORCEMENT_ENABLED is not set",
            }
        if not hasattr(self.provider, "add_user_rule"):
            return {"status": "unsupported", "reason": "Provider has no rule API"}
        applied = []
        try:
            for domain in targets:
                applied.append(self.provider.add_user_rule(domain))
        except ProviderError as error:
            return {
                "status": error.state,
                "reason": STATE_MESSAGES.get(error.state, str(error)),
                "applied": applied,
            }
        except ValueError as error:
            return {"status": "invalid", "reason": str(error), "applied": applied}
        return {
            "status": "applied",
            "provider": self.backend,
            "domains": targets,
            "applied": applied,
        }

    def rollback(self, domains):
        targets = self._domains(domains)
        if not targets or not self.available() or not self.enabled:
            return {"status": "unavailable", "reason": "Rollback is not enabled"}
        if not hasattr(self.provider, "remove_user_rule"):
            return {"status": "unsupported", "reason": "Provider has no rule API"}
        removed = []
        try:
            for domain in targets:
                removed.append(self.provider.remove_user_rule(domain))
        except ProviderError as error:
            return {
                "status": error.state,
                "reason": STATE_MESSAGES.get(error.state, str(error)),
                "removed": removed,
            }
        return {"status": "rolled_back", "provider": self.backend, "removed": removed}

    def restore_state(self, state):
        """Restore a snapshot's exact provider state when the provider supports it."""
        if not isinstance(state, dict) or not self.available() or not self.enabled:
            return {"status": "unavailable", "reason": "Restore is not enabled"}
        rules = state.get("user_rules")
        if not isinstance(rules, list):
            return {"status": "invalid", "reason": "Snapshot has no user-rule state"}
        if hasattr(self.provider, "restore_user_rules"):
            try:
                result = self.provider.restore_user_rules(rules)
                result["provider"] = self.backend
                return result
            except (ProviderError, ValueError) as error:
                reason = str(error) if isinstance(error, ValueError) else STATE_MESSAGES.get(error.state, str(error))
                return {"status": error.state if isinstance(error, ProviderError) else "invalid", "reason": reason}
        domains = [rule.strip("|^\n ") for rule in rules if rule.startswith("||")]
        return self.rollback(domains)

    def verify(self, domains):
        targets = self._domains(domains)
        if not targets or not self.available():
            return {"status": "not_verified", "reason": "No configured DNS provider"}
        if not hasattr(self.provider, "blocked_evidence"):
            return {"status": "not_verified", "reason": "Provider cannot inspect query log"}
        evidence = []
        try:
            for domain in targets:
                evidence.append(self.provider.blocked_evidence(domain))
        except ProviderError as error:
            return {
                "status": "not_verified",
                "reason": STATE_MESSAGES.get(error.state, str(error)),
            }
        verified = all(item.get("blocked") for item in evidence) if evidence else False
        return {
            "status": "verified" if verified else "not_verified",
            "provider": self.backend,
            "evidence": evidence,
        }
