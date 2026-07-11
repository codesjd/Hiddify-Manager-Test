import pytest
import json
from hiddifypanel import create_app
from hiddifypanel.models.config_enum import ConfigEnum
from hiddifypanel.models.outbound import OutboundProtocol, CustomOutbound
from hiddifypanel.models.proxy import ProxyTransport
from flask import current_app

@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        from hiddifypanel.database import db
        db.create_all()
        # Migration smoke 0 -> latest
        from hiddifypanel.panel.init_db import init_db
        init_db()
        yield app
        db.session.remove()
        db.drop_all()

def test_apply_scope_logic(app):
    from hiddifypanel.models.config_enum import subsystems_for_key, mark_dirty, get_pending_subsystems
    subs = subsystems_for_key(ConfigEnum.core_type)
    assert 'xray' in subs or 'singbox' in subs or 'common' in subs
    
    mark_dirty(ConfigEnum.core_type)
    pending = get_pending_subsystems()
    assert pending

def test_outbound_serialization(app):
    out = CustomOutbound(protocol=OutboundProtocol.vless, tag="test_vless", params={'host': 'example.com'}, transport=ProxyTransport.WS)
    xray_dict = out.to_xray_dict()
    assert isinstance(xray_dict, dict)
    
    singbox_dict = out.to_singbox_dict()
    assert isinstance(singbox_dict, dict)

def test_template_render(app):
    from hiddifypanel.panel.commercial.restapi.v2.user.singbox_api import singbox_configs
    from hiddifypanel.panel.commercial.restapi.v2.user.xray_api import v2ray_configs
    from hiddifypanel.models import User
    u = User.query.first()
    if u:
        sg_json = singbox_configs(u.uuid)
        assert json.loads(sg_json.json) # asserts it parses


def test_sqlite_usage_increment(app):
    '''Verify Plan 015 Phase 2: add_usage_json SQLite fallback increments counter.'''
    from uuid import uuid4
    from hiddifypanel.panel.usage import add_users_usage_new
    from hiddifypanel.models import User, db
    
    uid = str(uuid4())
    u = User(uuid=uid, name='smoke_test_026', usage_limit_GB=10, package_days=30, current_usage=0)
    db.session.add(u)
    db.session.commit()
    
    usage_before = u.current_usage
    add_users_usage_new([{'uuid': uid, 'usage': 1024}], child_id=0)
    db.session.refresh(u)
    assert u.current_usage == 1024, f"Expected 1024, got {u.current_usage} (SQLite fallback failed)"
