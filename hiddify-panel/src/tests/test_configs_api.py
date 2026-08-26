import os
from unittest.mock import patch
from flask import g

def test_all_configs_api(app):
    class MockIPASN:
        def asn(self, ip):
            return "unknown"

    with patch('hiddifypanel.hutils.network.auto_ip_selector.get_real_user_ip', return_value="127.0.0.1"), \
         patch('hiddifypanel.hutils.network.auto_ip_selector.get_asn_short_name', return_value="unknown"), \
         patch('hiddifypanel.hutils.network.auto_ip_selector.get_ipasn', return_value=MockIPASN(), create=True):

            with app.test_request_context():
                from hiddifypanel.models import User
                user = User.query.first()
                if user is None:
                    user = User(uuid="11111111-1111-1111-1111-111111111111", name="test_user")

                g.account = user
                g.proxy_path = "proxy"

                from hiddifypanel.panel.commercial.restapi.v2.user.configs_api import AllConfigsAPI
                view = AllConfigsAPI()

                from hiddifypanel.hutils.proxy.shared import get_hconfigs

                def patched_get_hconfigs(child_id):
                    res = get_hconfigs(child_id)
                    from hiddifypanel.models import ConfigEnum
                    if ConfigEnum.ssh_server_port not in res:
                        res[ConfigEnum.ssh_server_port] = 22
                    if ConfigEnum.proxy_path not in res:
                        res[ConfigEnum.proxy_path] = "proxy"
                    return res

                with patch('hiddifypanel.hutils.proxy.shared.get_hconfigs', side_effect=patched_get_hconfigs):
                    data = view.get()

                from hiddifypanel.panel.commercial.restapi.v2.user.configs_api import ConfigSchema
                data_dumped = data[0].json

                assert len(data_dumped) > 0, "No configs returned"

                # Check for standard config fields
                sample_item = data_dumped[0]
                assert "name" in sample_item
                assert "domain" in sample_item
                assert "link" in sample_item
                assert "protocol" in sample_item
                assert "transport" in sample_item
                assert "security" in sample_item
                assert "type" in sample_item
