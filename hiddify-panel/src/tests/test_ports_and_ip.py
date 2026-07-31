import pytest
from hiddifypanel.hutils.proxy.shared import ports_to_ranges
from hiddifypanel.hutils.network.net import add_number_to_ipv4, add_number_to_ipv6

def test_ports_to_ranges():
    assert ports_to_ranges("") == []
    assert ports_to_ranges("80") == ["80-80"]
    assert ports_to_ranges("80,81,82,443") == ["80-82", "443-443"]
    
    with pytest.raises(ValueError):
        ports_to_ranges("-1")

def test_add_number_to_ip():
    assert add_number_to_ipv4("1.1.1.1", 1) == "1.1.1.2"
    assert add_number_to_ipv4("1.1.1.255", 1) == "1.1.2.0"
    
    assert add_number_to_ipv6("2001:db8::1", 1) == "2001:db8::2"
    assert add_number_to_ipv6("2001:db8::ffff", 1) == "2001:db8::1:0"
