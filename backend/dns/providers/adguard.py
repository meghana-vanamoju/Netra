class AdGuardHomeAdapter:
    def __init__(self, url=None, password=None):
        self.url = url
        self.password = password
    def available(self):
        return bool(self.url)
    def collect(self):
        return []
