import pytest
import uuid
from flask import g
from hiddifypanel.models import User, Role
from hiddifypanel.models.config_enum import ConfigEnum
from hiddifypanel.models.config import set_hconfig
from hiddifypanel.models.domain import Domain
from hiddifypanel.database import db

def test_apps_api_unauthorized(app):
    with app.app_context():
        set_hconfig(ConfigEnum.proxy_path, "test_proxy")
        db.session.commit()
    with app.test_client() as client:
        res = client.get(f'/test_proxy/{uuid.uuid4()}/api/v2/user/apps/')
        assert res.status_code in [401, 403, 404]

def test_apps_api_authorized(app):
    with app.app_context():
        # Setup dummy user
        u = User(uuid=str(uuid.uuid4()), name="testuser")
        db.session.add(u)

        # Setup domain
        d = Domain(domain="test.example.com", alias="test")
        db.session.add(d)

        set_hconfig(ConfigEnum.proxy_path, "test_proxy")

        db.session.commit()

        uuid_str = u.uuid

    with app.test_client() as client:
        res = client.get(f'/test_proxy/{uuid_str}/api/v2/user/apps/?platform=all')
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) > 0

        # Test specific platform filtering (windows)
        res = client.get(f'/test_proxy/{uuid_str}/api/v2/user/apps/?platform=windows')
        assert res.status_code == 200
        data = res.get_json()
        assert any(app.get('title') == 'app.clash_verge_rev.title' for app in data)

        # Test specific platform filtering (android)
        res = client.get(f'/test_proxy/{uuid_str}/api/v2/user/apps/?platform=android')
        assert res.status_code == 200
        data = res.get_json()
        assert any(app.get('title') == 'HiddifyApp' for app in data)
        # NekoBox, cmfa, V2RayNG etc might be present, but singbox might be None or app.singbox.title

        # Test specific platform filtering (ios)
        res = client.get(f'/test_proxy/{uuid_str}/api/v2/user/apps/?platform=ios')
        assert res.status_code == 200
        data = res.get_json()
        assert any(app.get('title') == 'HiddifyApp' for app in data)

        # Test specific platform filtering (linux)
        res = client.get(f'/test_proxy/{uuid_str}/api/v2/user/apps/?platform=linux')
        assert res.status_code == 200
        data = res.get_json()
        assert any(app.get('title') == 'HiddifyApp' for app in data)

        # Test specific platform filtering (mac)
        res = client.get(f'/test_proxy/{uuid_str}/api/v2/user/apps/?platform=mac')
        assert res.status_code == 200
        data = res.get_json()
        assert any(app.get('title') == 'HiddifyApp' for app in data)

        # Test platform auto
        res = client.get(f'/test_proxy/{uuid_str}/api/v2/user/apps/?platform=auto')
        # This will fail since no user-agent is sent, returns 400
        assert res.status_code == 400

        # Test platform auto with windows User-Agent
        res = client.get(f'/test_proxy/{uuid_str}/api/v2/user/apps/?platform=auto', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
        assert res.status_code == 200
        data = res.get_json()
        assert any(app.get('title') == 'app.clash_verge_rev.title' for app in data)
