from enforcement.dns.manager import DNSEnforcementManager

def test_unavailable():
    m = DNSEnforcementManager()
    assert m.apply(["x"]).get("status") == "unavailable"