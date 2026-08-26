import pytest
from hiddifypanel.models.config_enum import ConfigEnum
from hiddifypanel.models.config import set_hconfig
from hiddifypanel.models.user import User
from hiddifypanel.database import db
from uuid import uuid4
import json
from unittest.mock import patch

def test_short_api_missing_auth(app):
    client = app.test_client()

    with app.app_context():
        set_hconfig(ConfigEnum.proxy_path_client, "client_path")
        db.session.commit()

    response = client.get('/client_path/api/v2/user/short/')
    assert response.status_code == 403

def test_short_api_with_auth(app):
    client = app.test_client()

    with app.app_context():
        set_hconfig(ConfigEnum.proxy_path_client, "client_path")
        db.session.commit()

        user_uuid = str(uuid4())
        u = User(uuid=user_uuid, name='test_short_user_auth', usage_limit_GB=10, package_days=30, current_usage=0)
        db.session.add(u)
        db.session.commit()

    with patch('hiddifypanel.panel.commercial.restapi.v2.user.short_api.hiddify.add_short_link') as mock_add_short_link, \
         patch('hiddifypanel.panel.commercial.restapi.v2.user.short_api.hiddify.get_account_panel_link') as mock_get_account_panel_link:

        mock_add_short_link.return_value = ("testshort", 300)
        mock_get_account_panel_link.return_value = "https://example.com/panel"

        response = client.get('/client_path/api/v2/user/short/', headers={'Hiddify-API-Key': user_uuid})
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data['short'] == 'testshort'
        assert data['full_url'] == 'https://localhost/testshort'
        assert data['expire_in'] == 300

        mock_add_short_link.assert_called_once_with("https://example.com/panel")
        mock_get_account_panel_link.assert_called_once()
