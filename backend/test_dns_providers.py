from dns.providers.adguard import AdGuardHomeAdapter
from dns.providers.pihole import PiHoleAdapter

def test_unavailable():
    assert AdGuardHomeAdapter().available() is False
    assert PiHoleAdapter().available() is False

def test_available():
    assert AdGuardHomeAdapter(url="http://x").available() is True
    assert PiHoleAdapter(url="http://x").available() is True