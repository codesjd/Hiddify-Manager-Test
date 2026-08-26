import pytest
from flask import g
from uuid import uuid4
from datetime import date, timedelta
from hiddifypanel.models import User, AdminUser, Lang, Role, Domain, DomainType
from hiddifypanel.database import db
from hiddifypanel.models import ConfigEnum, hconfig
import os

os.environ['TEST_MODE'] = '1'

def test_info_api_get(app):
    with app.test_client() as client:
        # Create a test user
        user_uuid = str(uuid4())
        u1 = User(uuid=user_uuid, name='test_user', usage_limit_GB=10.0, current_usage_GB=1.5, package_days=30, last_online=None, start_date=date.today())

        # Add a domain
        d1 = Domain(domain='example.com', mode=DomainType.direct)
        db.session.add(u1)
        db.session.add(d1)
        db.session.commit()

        proxy_path = hconfig(ConfigEnum.proxy_path_client)

        # Test authentication failure
        res = client.get(f'/{proxy_path}/api/v2/user/me/')
        assert res.status_code in [302, 401, 403, 404]

        res = client.get(f'/{proxy_path}/{user_uuid}/api/v2/user/me/', headers={'Hiddify-API-Key': user_uuid})
        assert res.status_code == 200
        data = res.json
        assert 'test_user' in data['profile_title']
        assert data['profile_usage_current'] == 1.5
        assert data['profile_usage_total'] == 10.0
        assert data['lang'] == 'en'
        assert 'profile_url' in data
        assert data['telegram_proxy_enable'] == False

def test_info_api_patch(app):
    with app.test_client() as client:
        # Create a test user
        user_uuid = str(uuid4())
        u1 = User(uuid=user_uuid, name='test_user_patch', usage_limit_GB=10.0, current_usage_GB=1.5, package_days=30, last_online=None, start_date=date.today(), telegram_id=123)
        db.session.add(u1)
        db.session.commit()

        proxy_path = hconfig(ConfigEnum.proxy_path_client)

        # Authenticate and test the API
        res = client.patch(f'/{proxy_path}/{user_uuid}/api/v2/user/me/', headers={'Hiddify-API-Key': user_uuid}, json={'telegram_id': 456, 'language': 'fa'})
        assert res.status_code == 200

        # Verify db changes
        db.session.refresh(u1)
        assert u1.telegram_id == 456
        assert u1.lang == Lang.fa
