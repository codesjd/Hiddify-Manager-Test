import pytest
from hiddifypanel.hutils.proxy.singbox import is_xray_proxy
from hiddifypanel.models import ProxyTransport

@pytest.mark.parametrize(
    "proxy_dict, expected",
    [
        ({}, False),
        ({"transport": "tcp"}, False),
        ({"transport": ProxyTransport.xhttp}, False),
        ({"name": "test_proxy", "proto": "vless"}, False),
    ],
)
def test_is_xray_proxy(proxy_dict, expected):
    """
    Test the is_xray_proxy function.
    Currently, this function is hardcoded to return False for all inputs.
    """
    assert is_xray_proxy(proxy_dict) == expected
