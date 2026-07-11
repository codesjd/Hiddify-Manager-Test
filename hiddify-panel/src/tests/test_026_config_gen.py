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
    '''Verify Plan 015 Phase 2: SQLite usage path replicates all three stored-procedure effects.'''
    from uuid import uuid4
    from datetime import datetime, date, timedelta
    from hiddifypanel.panel.usage import add_users_usage_new
    from hiddifypanel.models import User, db

    u1 = User(uuid=str(uuid4()), name='smoke_a', usage_limit_GB=10, package_days=30,
              current_usage=0, last_online=datetime.min, start_date=None)
    u2 = User(uuid=str(uuid4()), name='smoke_b', usage_limit_GB=10, package_days=30,
              current_usage=0, last_online=datetime.min, start_date=date.today() - timedelta(days=5))
    db.session.add_all([u1, u2])
    db.session.commit()

    before_batch = datetime.now()
    add_users_usage_new([
        {'uuid': u1.uuid, 'usage': 1024},
        {'uuid': u2.uuid, 'usage': 2048},
    ], child_id=0)
    after_batch = datetime.now()

    db.session.refresh(u1)
    db.session.refresh(u2)

    # Effect 1: counter incremented
    assert u1.current_usage == 1024, f"u1: expected 1024, got {u1.current_usage}"
    assert u2.current_usage == 2048, f"u2: expected 2048, got {u2.current_usage}"

    # Effect 2: last_online updated to batch time window
    assert u1.last_online >= before_batch and u1.last_online <= after_batch, \
        f"u1 last_online not in batch window: {u1.last_online}"
    assert u2.last_online >= before_batch and u2.last_online <= after_batch, \
        f"u2 last_online not in batch window: {u2.last_online}"

    # Effect 3: start_date conditional — set on NULL, untouched on existing
    today = date.today()
    assert u1.start_date == today, f"u1 start_date should be set to today ({today}), got {u1.start_date}"
    assert u2.start_date == date.today() - timedelta(days=5), \
        f"u2 start_date should be untouched, got {u2.start_date}"
