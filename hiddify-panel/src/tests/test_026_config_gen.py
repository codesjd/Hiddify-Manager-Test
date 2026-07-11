import pytest
import json
from datetime import datetime, date, timedelta
from uuid import uuid4
from hiddifypanel import create_app
from hiddifypanel.models.config_enum import ConfigEnum
from hiddifypanel.models.routing import OutboundProtocol, CustomOutbound
from hiddifypanel.models.proxy import ProxyTransport

@pytest.fixture
def app():
    import os
    os.environ['STDOUT_LOG_LEVEL'] = 'INFO'
    app = create_app(SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', TESTING=True, STDOUT_LOG_LEVEL='INFO', HIDDIFY_CONFIG_PATH='/opt/hiddify-manager')
    with app.app_context():
        from hiddifypanel.database import db
        db.create_all()
        from hiddifypanel.panel.init_db import init_db
        init_db()
        yield app
        db.session.remove()
        db.drop_all()

def test_apply_scope_logic(app):
    from hiddifypanel.hutils import apply_scope
    subs = apply_scope.subsystems_for_key(ConfigEnum.core_type)
    assert subs is not None
    apply_scope.mark_dirty(list(subs))
    pending = apply_scope.get_pending_subsystems()
    assert pending is not None

def test_outbound_serialization(app):
    out = CustomOutbound(protocol=OutboundProtocol.vless, tag='test_vless', params={'host': 'example.com'}, transport=ProxyTransport.WS)
    xray_dict = out.to_xray_dict()
    assert isinstance(xray_dict, dict)
    singbox_dict = out.to_singbox_dict()
    assert isinstance(singbox_dict, dict)

def test_migration_smoke(app):
    from hiddifypanel.models import hconfig
    assert hconfig(ConfigEnum.is_parent) is not None

def test_sqlite_usage_increment(app):
    '''Verify Plan 015 Phase 2: SQLite usage path replicates all three stored-procedure effects.'''
    from hiddifypanel.panel.usage import add_users_usage_new
    from hiddifypanel.models import User, db

    u1 = User(uuid=str(uuid4()), name='smoke_a', usage_limit_GB=10, package_days=30, current_usage=0, last_online=datetime.min, start_date=None)
    u2 = User(uuid=str(uuid4()), name='smoke_b', usage_limit_GB=10, package_days=30, current_usage=0, last_online=datetime.min, start_date=date.today() - timedelta(days=5))
    db.session.add_all([u1, u2])
    db.session.commit()

    before_batch = datetime.now()
    add_users_usage_new([
        {'uuid': u1.uuid, 'usage': 1024}, {'uuid': u2.uuid, 'usage': 2048}, ], child_id=0)
    after_batch = datetime.now()

    db.session.refresh(u1)
    db.session.refresh(u2)

    # Effect 1: counter incremented
    assert u1.current_usage == 1024, f"u1: expected 1024, got {u1.current_usage}"
    assert u2.current_usage == 2048, f"u2: expected 2048, got {u2.current_usage}"

    # Effect 2: last_online updated to batch time window
    assert before_batch <= u1.last_online <= after_batch, f"u1 last_online not in batch window: {u1.last_online}"
    assert before_batch <= u2.last_online <= after_batch, f"u2 last_online not in batch window: {u2.last_online}"

    # Effect 3: start_date conditional — set on NULL, untouched on existing
    today = date.today()
    assert u1.start_date == today, f"u1 start_date should be {today}, got {u1.start_date}"
    assert u2.start_date == date.today() - timedelta(days=5), f"u2 start_date should be untouched, got {u2.start_date}"
