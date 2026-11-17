class DNSEnforcementManager:
    def __init__(self, provider=None):
        self.provider = provider
    def apply(self, domains):
        if not self.provider:
            return {"status": "unavailable", "reason": "No provider configured"}
        return {"status": "not_verified", "reason": "Provider integration not verified"}
    def rollback(self):
        return {"status": "not_verified"}
