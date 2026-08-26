import pytest
from flask import g
from hiddifypanel.models import User, AdminUser, Role, ConfigEnum
from hiddifypanel.models import hconfig

def test_info_api_get(app):
    client = app.test_client()
    with app.app_context():
        from hiddifypanel.database import db
        from hiddifypanel.panel.init_db import init_db
        init_db()
        User.query.delete()
        u = User(uuid="11111111-1111-1111-1111-111111111111", name="test_user", enable=True, telegram_id=12345)
        db.session.add(u)
        db.session.commit()
        proxy_path = hconfig(ConfigEnum.proxy_path_client)

    res = client.get(f'/{proxy_path}/11111111-1111-1111-1111-111111111111/api/v2/user/me/', headers={'Hiddify-API-Key': '11111111-1111-1111-1111-111111111111'})
    assert res.status_code == 200
    data = res.json
    assert data['profile_title'] == 'test_user'
    assert data['telegram_id'] == 12345
    assert data['profile_usage_current'] == 0.0
    assert data['profile_usage_total'] == 1000.0
    assert data['telegram_proxy_enable'] == False

def test_info_api_patch(app):
    client = app.test_client()
    with app.app_context():
        from hiddifypanel.database import db
        from hiddifypanel.panel.init_db import init_db
        init_db()
        User.query.delete()
        u = User(uuid="11111111-1111-1111-1111-111111111111", name="test_user", enable=True, telegram_id=12345)
        db.session.add(u)
        db.session.commit()
        proxy_path = hconfig(ConfigEnum.proxy_path_client)

    res = client.patch(
        f'/{proxy_path}/11111111-1111-1111-1111-111111111111/api/v2/user/me/',
        headers={'Hiddify-API-Key': '11111111-1111-1111-1111-111111111111'},
        json={'telegram_id': 54321, 'language': 'fa'}
    )
    assert res.status_code == 200
    assert res.json['message'] == 'ok'

    with app.app_context():
        u = User.by_uuid("11111111-1111-1111-1111-111111111111")
        assert u.telegram_id == 54321
        assert u.lang.value == 'fa'
