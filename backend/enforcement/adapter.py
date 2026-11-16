import os

class DNSBackendAdapter:
    def __init__(self):
        self.backend = os.environ.get("NETRA_DNS_BACKEND")

    def available(self):
        return bool(self.backend)

    def apply_policy(self, domains):
        if not self.backend:
            return {"status": "unavailable", "reason": "No backend configured"}
        return {"status": "not_implemented", "reason": "Backend integration requires configured supported engine"}
