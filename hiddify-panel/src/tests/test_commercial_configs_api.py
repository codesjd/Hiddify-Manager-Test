import pytest
from hiddifypanel.models import User, Domain, BoolConfig, StrConfig, ConfigEnum
from hiddifypanel.database import db
from uuid import uuid4
from hiddifypanel.models import hconfig
from unittest.mock import patch

def test_get_all_configs(app):
    with app.app_context():
        client = app.test_client()

        u1 = User(uuid=str(uuid4()), name='test_user', usage_limit_GB=10, package_days=30, current_usage=0)
        db.session.add(u1)

        proxy_path = hconfig(ConfigEnum.proxy_path)
        if not proxy_path:
             db.session.add(StrConfig(key=ConfigEnum.proxy_path, value='test-proxy'))
             proxy_path = 'test-proxy'

        if not hconfig(ConfigEnum.ssh_server_port):
             db.session.add(StrConfig(key=ConfigEnum.ssh_server_port, value='2222'))

        if not Domain.query.first():
             d1 = Domain(domain="example.com", alias="example", mode="direct")
             db.session.add(d1)

        db.session.commit()

        with patch('hiddifypanel.hutils.proxy.shared._get_valid_proxies_uncached', return_value=[]):
            url = f"/{proxy_path}/{u1.uuid}/api/v2/user/all-configs/"
            response = client.get(url)

            assert response.status_code == 200
            data = response.get_json()
            assert len(data) > 0

            names = [item['name'] for item in data]
            assert 'Auto' in names
            assert 'Subscription link b64' in names
