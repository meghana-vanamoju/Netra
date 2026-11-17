class PiHoleAdapter:
    def __init__(self, url=None, token=None):
        self.url = url
        self.token = token
    def available(self):
        return bool(self.url)
    def collect(self):
        return []
