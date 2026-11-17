from discovery.unified import merge_devices

def test_merge():
    a = [{"ip_address":"10.0.0.1","mac_address":"AA","discovery_source":"lan"}]
    b = [{"ip_address":"10.0.0.1","hostname":"phone","discovery_source":"router"}]
    out = merge_devices(a,b)
    assert len(out) == 1
    assert out[0]["hostname"] == "phone"
    assert "lan" in out[0]["sources"]
    assert "router" in out[0]["sources"]