from discovery.unified import merge_devices


def test_merge():
    a = [{"ip_address": "10.0.0.1", "mac_address": "AA", "discovery_source": "lan"}]
    b = [{"ip_address": "10.0.0.1", "hostname": "phone", "discovery_source": "router"}]
    out = merge_devices(a, b)
    assert len(out) == 1
    assert out[0]["hostname"] == "phone"
    assert "lan" in out[0]["sources"]
    assert "router" in out[0]["sources"]


def test_merge_preserves_partial_values_and_tracks_dhcp_address_change():
    router = [
        {
            "ip_address": "192.168.88.20",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "hostname": "tablet",
            "discovery_source": "router:adguard-home",
        }
    ]
    lan = [
        {
            "ip_address": "192.168.88.27",
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "hostname": None,
            "vendor": None,
            "discovery_source": "lan-discovery",
        }
    ]

    merged = merge_devices(router, lan)

    assert len(merged) == 1
    assert merged[0]["ip_address"] == "192.168.88.27"
    assert merged[0]["hostname"] == "tablet"
    assert set(merged[0]["sources"]) == {"router:adguard-home", "lan-discovery"}


def test_merge_does_not_merge_conflicting_macs_at_same_ip():
    merged = merge_devices(
        [{"ip_address": "192.168.88.30", "mac_address": "AA:AA"}],
        [{"ip_address": "192.168.88.30", "mac_address": "BB:BB"}],
    )
    assert len(merged) == 2
